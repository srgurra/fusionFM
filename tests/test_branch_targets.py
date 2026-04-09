import asyncio
import json
from dataclasses import dataclass
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from fusionframe import App, HTTPException, TestClient
from fusionframe.db import transaction
from fusionframe.http import JSONResponse, Request, Response, UploadedFile, WebSocket, _json_default, parse_http_body
from fusionframe.pagination import get_pagination_params, paginate


def test_grouped_package_exports_are_importable():
    from fusionframe.core import App as CoreApp, Router, TestClient as CoreTestClient
    from fusionframe.data import Model, paginate as data_paginate
    from fusionframe.integrations import GraphQL, TemplateEngine, mount_spa, mount_static
    from fusionframe.operations import JobQueue, rate_limit
    from fusionframe.security import Identity, session_middleware

    assert CoreApp.__name__ == "App"
    assert Router.__name__ == "Router"
    assert CoreTestClient.__name__ == "TestClient"
    assert Model.__name__ == "Model"
    assert data_paginate is paginate
    assert GraphQL.__name__ == "GraphQL"
    assert TemplateEngine.__name__ == "TemplateEngine"
    assert callable(mount_spa)
    assert callable(mount_static)
    assert JobQueue.__name__ == "JobQueue"
    assert callable(rate_limit)
    assert Identity.__name__ == "Identity"
    assert callable(session_middleware)


def test_router_uses_indexed_static_dynamic_and_wildcard_routes():
    from fusionframe.routing import Router

    router = Router()

    async def home(request):
        return {"ok": True}

    async def user_detail(request):
        return {"ok": True}

    async def asset(request):
        return {"ok": True}

    router.add_route("GET", "/", home)
    router.add_route("GET", "/users/{user_id:int}", user_detail)
    router.add_route("GET", "/assets/{path:path}", asset)

    exact_route, exact_params = router.match("GET", "/")
    trailing_route, trailing_params = router.match("GET", "/users/42/")
    wildcard_route, wildcard_params = router.match("GET", "/assets/css/site.css")
    missing_route, missing_params = router.match("GET", "/missing")

    assert exact_route["handler"] is home
    assert exact_params == {}
    assert trailing_route["handler"] is user_detail
    assert trailing_params == {"user_id": "42"}
    assert wildcard_route["handler"] is asset
    assert wildcard_params == {"path": "css/site.css"}
    assert missing_route is None
    assert missing_params is None
    assert router._static_routes[(( "http", "GET"), "/")]["handler"] is home
    assert router._dynamic_routes[(("http", "GET"))][2][0]["handler"] is user_detail
    assert router._wildcard_routes[(("http", "GET"))][0]["handler"] is asset


def test_frontend_and_static_error_paths(tmp_path):
    app = App()
    mount_root = tmp_path / "spa"
    mount_root.mkdir()

    from fusionframe.frontend import mount_spa
    from fusionframe.static import mount_static

    mount_spa(app, str(mount_root), mount_path="/app", assets_path="/assets")
    mount_static(app, str(mount_root), url_path="/files")
    client = TestClient(app)

    missing_index = client.get("/app")
    assert missing_index.status_code == 404
    assert missing_index.json()["error"] == "Frontend entrypoint not found"

    missing_static = client.get("/files/missing.txt")
    assert missing_static.status_code == 404

    forbidden_static = client.get("/files/../secret.txt")
    assert forbidden_static.status_code == 403


def test_graphql_invalid_and_unknown_queries():
    from fusionframe.graphql import GraphQL

    app = App()
    graphql = GraphQL()

    @graphql.query("ping")
    async def ping(request):
        return {"pong": True}

    graphql.mount(app)
    client = TestClient(app)

    invalid = client.post("/graphql", json_body={"query": "ping"})
    unknown = client.post("/graphql", json_body={"query": "{ nope }"})

    assert invalid.status_code == 400
    assert invalid.json()["error"] == "Invalid GraphQL query"
    assert unknown.status_code == 400
    assert unknown.json()["error"] == "Unknown GraphQL field"


def test_pagination_guards_invalid_query_values():
    request = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/items",
            "query_string": b"page=0&per_page=bad",
            "headers": [],
        }
    )

    params = get_pagination_params(request, default_page=2, default_per_page=15, max_per_page=50)
    page = paginate(list(range(3)), page=1, per_page=0)

    assert params == {"page": 1, "per_page": 15}
    assert page["pages"] == 0


def test_http_helper_branches(tmp_path):
    text_data, text_form, text_files = parse_http_body({"content-type": "text/plain"}, b"hello")
    raw_data, raw_form, raw_files = parse_http_body({"content-type": "application/octet-stream"}, b"\x00\x01")
    empty_data, empty_form, empty_files = parse_http_body({}, b"")

    assert text_data == {"text": "hello"}
    assert text_form == {}
    assert text_files == {}
    assert raw_data == {"raw": b"\x00\x01"}
    assert raw_form == {}
    assert raw_files == {}
    assert empty_data == {}
    assert empty_form == {}
    assert empty_files == {}

    upload = UploadedFile("hello.txt", b"hello", "text/plain")
    destination = tmp_path / "hello.txt"
    upload.save(destination)
    assert destination.read_bytes() == b"hello"
    assert upload.read() == b"hello"

    @dataclass
    class Payload:
        name: str

    assert _json_default(Payload("Sri")) == {"name": "Sri"}

    class DictLike:
        def to_dict(self):
            return {"ok": True}

    assert _json_default(DictLike()) == {"ok": True}

    with pytest.raises(TypeError):
        _json_default(object())

    response = JSONResponse({"message": "ok"})
    assert json.loads(response.render().decode("utf-8")) == {"message": "ok"}
    assert Response(b"bytes").render() == b"bytes"


def test_websocket_helper_branches():
    sent = []
    incoming = [
        {"type": "websocket.receive", "bytes": b"abc"},
        {"type": "websocket.receive", "text": json.dumps({"ok": True})},
        {"type": "websocket.disconnect"},
    ]

    async def receive():
        return incoming.pop(0)

    async def send(message):
        sent.append(message)

    async def run():
        socket = WebSocket(
            {"type": "websocket", "path": "/ws", "query_string": b"a=1", "headers": [(b"x-test", b"yes")]},
            receive,
            send,
        )
        assert socket.get_header("x-test") == "yes"
        await socket.accept(subprotocol="chat", headers={"x-extra": "1"})
        await socket.accept()
        assert await socket.receive_bytes() == b"abc"
        assert await socket.receive_json() == {"ok": True}
        assert await socket.receive_text() is None
        await socket.send_bytes(b"pong")
        await socket.send_json({"done": True})
        await socket.close(code=1001, reason="bye")
        await socket.close()

    asyncio.run(run())

    assert sent[0]["type"] == "websocket.accept"
    assert sent[0]["subprotocol"] == "chat"
    assert sent[1] == {"type": "websocket.send", "bytes": b"pong"}
    assert sent[2]["type"] == "websocket.send"
    assert json.loads(sent[2]["text"]) == {"done": True}
    assert len(sent) == 3


def test_transaction_context_with_owned_and_external_sessions(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'tx.db'}", echo=False)
    session_local = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    import fusionframe.db as db_module

    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE items (value INTEGER NOT NULL)"))

    monkeypatch.setattr(db_module, "SessionLocal", session_local)

    with transaction() as session:
        session.execute(text("INSERT INTO items (value) VALUES (1)"))

    with engine.connect() as connection:
        assert connection.execute(text("SELECT COUNT(*) FROM items")).scalar_one() == 1

    external = session_local()
    try:
        with transaction(external) as session:
            session.execute(text("INSERT INTO items (value) VALUES (2)"))
        external.commit()
    finally:
        external.close()

    with engine.connect() as connection:
        assert connection.execute(text("SELECT COUNT(*) FROM items")).scalar_one() == 2

    engine.dispose()


def test_http_exception_response_shape():
    app = App()

    @app.get("/forbidden")
    async def forbidden(request):
        raise HTTPException(403, "Forbidden", headers={"x-reason": "policy"})

    client = TestClient(app)
    response = client.get("/forbidden")

    assert response.status_code == 403
    assert response.json() == {"error": "Forbidden"}
    assert response.headers["x-reason"] == "policy"
