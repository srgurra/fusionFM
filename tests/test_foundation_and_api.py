import asyncio
from contextlib import contextmanager
from dataclasses import dataclass

from pydantic import BaseModel
from fusionframe import (
    API_COMPAT_VERSION,
    DEPRECATION_POLICY,
    PUBLIC_API,
    __version__,
    App,
    AppSettings,
    GraphQL,
    Plugin,
    TestClient,
    deprecated,
    require_auth,
    require_permission,
)
from fusionframe.stability import STABLE_MODULES, is_public_symbol


def test_public_api_exports_are_stable():
    assert __version__ == "0.1.0a1"
    assert API_COMPAT_VERSION == "1"
    assert AppSettings.__name__ == "AppSettings"
    assert Plugin.__name__ == "Plugin"
    assert GraphQL.__name__ == "GraphQL"
    assert "deprecation period" in DEPRECATION_POLICY.lower()
    assert "App" in PUBLIC_API


def test_public_api_contract_matches_exports():
    import fusionframe

    assert tuple(fusionframe.__all__) == PUBLIC_API
    for name in PUBLIC_API:
        assert hasattr(fusionframe, name)
        assert is_public_symbol(name) is True
    assert is_public_symbol("routing") is False


def test_stable_module_boundary_is_documented():
    assert STABLE_MODULES == ("fusionframe", "fusionframe.db", "fusionframe.orm")


def test_settings_disable_docs_and_enable_debug(monkeypatch):
    monkeypatch.setenv("FUSIONFRAME_DEBUG", "true")
    monkeypatch.setenv("FUSIONFRAME_DOCS_ENABLED", "false")
    settings = AppSettings.from_env()
    app = App(settings=settings)

    @app.get("/boom")
    async def boom(request):
        raise RuntimeError("broken")

    client = TestClient(app)
    docs_response = client.get("/docs")
    boom_response = client.get("/boom")

    assert docs_response.status_code == 404
    assert boom_response.status_code == 500
    assert boom_response.json()["detail"] == "broken"


def test_dependency_injection_context_cleanup_runs():
    app = App()
    events = []

    @contextmanager
    def resource():
        events.append("enter")
        try:
            yield "db"
        finally:
            events.append("exit")

    @app.get("/resource", dependencies={"db": resource})
    async def with_resource(request, db):
        events.append(db)
        return {"ok": True}

    client = TestClient(app)
    response = client.get("/resource")

    assert response.status_code == 200
    assert events == ["enter", "db", "exit"]


def test_middleware_order_is_nested_and_short_circuitable():
    app = App()
    events = []

    async def outer(request, call_next):
        events.append("outer:before")
        response = await call_next()
        events.append("outer:after")
        return response

    async def inner(request, call_next):
        events.append("inner:before")
        response = await call_next()
        events.append("inner:after")
        return response

    app.use(outer)
    app.use(inner)

    @app.get("/ordered")
    async def ordered(request):
        events.append("handler")
        return {"ok": True}

    client = TestClient(app)
    response = client.get("/ordered")

    assert response.status_code == 200
    assert events == [
        "outer:before",
        "inner:before",
        "handler",
        "inner:after",
        "outer:after",
    ]

    blocked = App()
    blocked_events = []

    async def blocker(request, call_next):
        blocked_events.append("blocked")
        return {"blocked": True}, 401

    async def unreachable(request, call_next):
        blocked_events.append("should-not-run")
        return await call_next()

    blocked.use(blocker)
    blocked.use(unreachable)

    @blocked.get("/blocked")
    async def blocked_handler(request):
        blocked_events.append("handler")
        return {"ok": True}

    blocked_client = TestClient(blocked)
    blocked_response = blocked_client.get("/blocked")

    assert blocked_response.status_code == 401
    assert blocked_response.json() == {"blocked": True}
    assert blocked_events == ["blocked"]


def test_plugin_hooks_and_route_registration():
    app = App()

    class SamplePlugin(Plugin):
        def setup(self, app):
            app.state["plugin_setup"] = True

            @app.get("/plugin")
            async def plugin_route(request):
                return {
                    "setup": app.state["plugin_setup"],
                    "started": app.state.get("plugin_started", False),
                }

        async def startup(self, app):
            app.state["plugin_started"] = True

        async def shutdown(self, app):
            app.state["plugin_stopped"] = True

    app.plugin(SamplePlugin)

    sent = []
    messages = [{"type": "lifespan.startup"}, {"type": "lifespan.shutdown"}]

    async def receive():
        return messages.pop(0)

    async def send(message):
        sent.append(message)

    asyncio.run(app({"type": "lifespan"}, receive, send))

    client = TestClient(app)
    response = client.get("/plugin")

    assert sent[0]["type"] == "lifespan.startup.complete"
    assert response.status_code == 200
    assert response.json()["setup"] is True
    assert app.state["plugin_stopped"] is True


def test_lifespan_startup_and_shutdown_are_idempotent():
    app = App()
    events = []

    @app.on_startup
    async def startup():
        events.append("startup")

    @app.on_shutdown
    async def shutdown():
        events.append("shutdown")

    sent = []
    messages = [
        {"type": "lifespan.startup"},
        {"type": "lifespan.startup"},
        {"type": "lifespan.shutdown"},
        {"type": "lifespan.shutdown"},
    ]

    async def receive():
        return messages.pop(0)

    async def send(message):
        sent.append(message)

    asyncio.run(app({"type": "lifespan"}, receive, send))

    assert [message["type"] for message in sent] == [
        "lifespan.startup.complete",
        "lifespan.startup.complete",
        "lifespan.shutdown.complete",
    ]
    assert events == ["startup", "shutdown"]
    assert app.state.is_started is False


def test_startup_failure_stops_lifecycle_and_preserves_not_started_state():
    app = App()

    @app.on_startup
    async def startup():
        raise RuntimeError("startup failed")

    sent = []
    messages = [{"type": "lifespan.startup"}]

    async def receive():
        return messages.pop(0)

    async def send(message):
        sent.append(message)

    asyncio.run(app({"type": "lifespan"}, receive, send))

    assert sent == [{"type": "lifespan.startup.failed", "message": "startup failed"}]
    assert app.state.is_started is False


def test_deprecated_routes_surface_metadata():
    app = App()

    @app.get("/legacy")
    @deprecated(reason="Use /new")
    async def legacy(request):
        return {"ok": True}

    client = TestClient(app)
    response = client.get("/legacy")
    openapi = client.get("/openapi.json").json()

    assert response.headers["deprecation"] == "true"
    assert response.headers["x-deprecation-reason"] == "Use /new"
    assert openapi["paths"]["/legacy"]["get"]["deprecated"] is True


def test_openapi_generates_request_response_and_security_schemas():
    class CreateItem(BaseModel):
        name: str
        count: int

    @dataclass
    class ItemResponse:
        id: int
        name: str

    app = App()

    @app.post("/items/{item_id:int}", model=CreateItem, response_model=ItemResponse)
    @require_auth
    @require_permission("items:write")
    async def create_item(request) -> ItemResponse:
        return ItemResponse(id=int(request.params["item_id"]), name=request.body["name"])

    client = TestClient(app)
    openapi = client.get("/openapi.json").json()
    operation = openapi["paths"]["/items/{item_id:int}"]["post"]

    assert operation["requestBody"]["content"]["application/json"]["schema"]["$ref"] == "#/components/schemas/CreateItem"
    assert operation["responses"]["200"]["content"]["application/json"]["schema"]["$ref"] == "#/components/schemas/ItemResponse"
    assert operation["parameters"] == [
        {
            "name": "item_id",
            "in": "path",
            "required": True,
            "schema": {"type": "integer"},
        }
    ]
    assert operation["security"] == [{"bearerAuth": []}, {"sessionAuth": []}]
    assert operation["x-required-permissions"] == ["items:write"]
    assert "CreateItem" in openapi["components"]["schemas"]
    assert "ItemResponse" in openapi["components"]["schemas"]
    assert openapi["components"]["securitySchemes"]["bearerAuth"]["scheme"] == "bearer"
    assert openapi["components"]["securitySchemes"]["sessionAuth"]["in"] == "cookie"
