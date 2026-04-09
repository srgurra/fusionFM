import asyncio

from fusionframe import (
    App,
    TestClient,
    auth_middleware,
    security_headers_middleware,
    session_middleware,
    set_session_user,
)


def test_session_auth_and_security_headers():
    app = App(max_body_size=128)
    app.use(session_middleware(secure=False))
    app.use(security_headers_middleware)
    app.use(auth_middleware)

    @app.post("/login")
    async def login(request):
        set_session_user(request, {"sub": "user-1", "roles": ["admin"]})
        return {"ok": True}

    @app.get("/me")
    async def me(request):
        return {"user": request.user}

    client = TestClient(app)

    login_response = client.post("/login", json_body={})
    assert login_response.status_code == 200
    assert "set-cookie" in login_response.headers
    assert login_response.headers["x-content-type-options"] == "nosniff"
    cookie = login_response.headers["set-cookie"].split(";", 1)[0]

    me_response = client.get("/me", headers={"cookie": cookie})
    assert me_response.status_code == 200
    assert me_response.json()["user"]["sub"] == "user-1"


def test_oversized_body_returns_413():
    app = App(max_body_size=8)

    @app.post("/echo")
    async def echo(request):
        return {"ok": True}

    client = TestClient(app)
    response = client.post("/echo", json_body={"abcdef": 1})

    assert response.status_code == 413
    assert "Request body too large" in response.json()["error"]


def test_websocket_echo_flow():
    app = App()

    @app.websocket("/ws/{name}")
    async def echo(socket):
        await socket.accept()
        await socket.send_json({"hello": socket.params["name"]})
        payload = await socket.receive_json()
        await socket.send_json({"echo": payload})

    messages = [
        {"type": "websocket.connect"},
        {"type": "websocket.receive", "text": '{"x": 1}'},
        {"type": "websocket.disconnect", "code": 1000},
    ]
    sent = []

    async def receive():
        return messages.pop(0)

    async def send(message):
        sent.append(message)

    asyncio.run(
        app(
            {"type": "websocket", "path": "/ws/alice", "query_string": b"", "headers": []},
            receive,
            send,
        )
    )

    assert sent[0]["type"] == "websocket.accept"
    assert sent[1]["text"] == '{"hello": "alice"}'
    assert sent[2]["text"] == '{"echo": {"x": 1}}'
    assert sent[-1]["type"] == "websocket.close"
