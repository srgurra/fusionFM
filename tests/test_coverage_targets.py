import asyncio
import importlib
import inspect
import json
import subprocess
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Union

import pytest
from click.testing import CliRunner
from pydantic import BaseModel

from fusionframe import App, TestClient
from fusionframe.cli import cli

auth_module = importlib.import_module("fusionframe.auth")
authorization_module = importlib.import_module("fusionframe.authorization")
docs_module = importlib.import_module("fusionframe.docs")
exceptions_module = importlib.import_module("fusionframe.exceptions")
sessions_module = importlib.import_module("fusionframe.sessions")
versioning_module = importlib.import_module("fusionframe.versioning")


def test_auth_helpers_cover_error_and_edge_paths():
    identity = auth_module.Identity(subject="u1", claims={"name": "Sri"})
    assert auth_module.normalize_identity(None) is None
    assert auth_module.normalize_identity(identity) is identity
    assert auth_module.normalize_identity({"sub": "u2", "roles": "admin"}).roles == ["admin"]
    with pytest.raises(TypeError):
        auth_module.normalize_identity(object())

    token = auth_module.create_token(identity, subject="override")
    assert auth_module.verify_token(token)["sub"] == "override"
    assert auth_module.verify_token("broken") is None
    assert auth_module._normalize_list(None) == []
    assert auth_module._normalize_list("x") == ["x"]

    hasher = auth_module.PasswordHasher()
    encoded = hasher.hash("secret")
    assert hasher.verify("secret", encoded) is True
    assert hasher.verify("secret", "bad-format") is False
    assert hasher.verify("secret", encoded.replace("pbkdf2_sha256", "sha1", 1)) is False

    backend = auth_module.InMemoryAuthBackend()
    backend.register("user@example.com", "secret")
    assert asyncio.run(backend.get_identity("missing")) is None
    with pytest.raises(KeyError):
        asyncio.run(backend.set_password("missing", "x"))

    reset_manager = auth_module.PasswordResetManager()
    reset_token = reset_manager.issue_token("user@example.com")
    assert reset_manager.verify_token(reset_token) == "user@example.com"
    assert reset_manager.verify_token(auth_module.create_token({"sub": "x"})) is None
    assert asyncio.run(reset_manager.reset_password(backend, "wrong@example.com", reset_token, "new")) is False

    class MinimalBackend(auth_module.AuthBackend):
        pass

    with pytest.raises(NotImplementedError):
        asyncio.run(MinimalBackend().authenticate("x", "y"))
    with pytest.raises(NotImplementedError):
        asyncio.run(MinimalBackend().get_identity("x"))
    with pytest.raises(NotImplementedError):
        asyncio.run(MinimalBackend().set_password("x", "y"))

    account_manager = auth_module.AccountManager(backend)
    bad_token = account_manager.issue_verification_token("missing@example.com")
    assert asyncio.run(account_manager.mark_verified(bad_token)) is False
    assert asyncio.run(account_manager.change_password("user@example.com", "wrong", "newer")) is False
    assert asyncio.run(account_manager.get_account("missing@example.com")) is None

    class NoRegisterBackend(auth_module.AuthBackend):
        async def authenticate(self, identifier, secret):
            return None

        async def get_identity(self, identifier):
            return None

        async def set_password(self, identifier, password):
            return None

    with pytest.raises(TypeError):
        asyncio.run(auth_module.AccountManager(NoRegisterBackend()).register("x", "y"))


def test_authorization_helpers_cover_direct_wrappers():
    request = SimpleNamespace(user=None, params={"resource": "projects"})

    @authorization_module.require_auth
    async def protected(request):
        return {"ok": True}

    with pytest.raises(exceptions_module.HTTPException) as exc:
        asyncio.run(protected(request))
    assert exc.value.status_code == 401

    request.user = {"roles": ["member"], "permissions": ["projects:*", "*:read"]}

    @authorization_module.require_role("admin")
    async def admin_only(request):
        return {"ok": True}

    with pytest.raises(exceptions_module.HTTPException):
        asyncio.run(admin_only(request))

    @authorization_module.require_permission("tickets:write")
    async def ticket_write(request):
        return {"ok": True}

    with pytest.raises(exceptions_module.HTTPException):
        asyncio.run(ticket_write(request))

    assert authorization_module.authorize(None) is False
    assert authorization_module.authorize({"roles": ["member"]}, roles=["admin"]) is False
    assert authorization_module.has_resource_permission(request.user, "projects", "write") is True
    assert authorization_module.has_resource_permission({"permissions": ["*:*"]}, "x", "y") is True

    async def resource_getter(request):
        return request.params["resource"]

    @authorization_module.require_resource_permission("read", resource_getter)
    async def scoped(request):
        return {"ok": True}

    assert asyncio.run(scoped(request)) == {"ok": True}

    class Policy(authorization_module.AuthorizationPolicy):
        async def authorize(self, request, user):
            return False

    with pytest.raises(NotImplementedError):
        asyncio.run(authorization_module.AuthorizationPolicy().authorize(None, None))
    assert asyncio.run(authorization_module.evaluate_policy(lambda req, user: True, None, None)) is True

    @authorization_module.require_policy(Policy())
    async def denied(request):
        return {"ok": True}

    with pytest.raises(exceptions_module.HTTPException):
        asyncio.run(denied(request))


def test_session_and_docs_internal_helpers():
    assert sessions_module._parse_cookies("a=1; b=2; broken") == {"a": "1", "b": "2"}
    encoded = sessions_module._encode_session({"user": "sri"})
    assert sessions_module._decode_session(encoded)["user"] == "sri"
    assert sessions_module._decode_session("broken") == {}
    tampered = encoded[:-1] + ("x" if encoded[-1] != "x" else "y")
    assert sessions_module._decode_session(tampered) == {}

    store = sessions_module.InMemorySessionStore()
    sid = store.create_session_id()
    store.save(sid, {"x": 1}, ttl=0)
    assert store.load(sid) is None
    store.delete(sid)

    class DemoModel(BaseModel):
        name: str

    @dataclass
    class DemoData:
        name: str
        count: int = 1

    schemas = {}
    assert docs_module._security_schemes([{"security": []}]) == {}
    assert docs_module._converter_schema("float") == {"type": "number"}
    assert docs_module._path_parameters("/items/{id:int}/{slug}") == [
        {"name": "id", "in": "path", "required": True, "schema": {"type": "integer"}},
        {"name": "slug", "in": "path", "required": True, "schema": {"type": "string"}},
    ]
    assert docs_module._schema_for_type(list[int], schemas)["type"] == "array"
    assert docs_module._schema_for_type(dict[str, int], schemas)["type"] == "object"
    assert "oneOf" in docs_module._schema_for_type(Union[int, str], schemas)
    assert docs_module._schema_for_type(Union[int, None], schemas) == {"type": "integer"}
    assert docs_module._schema_for_type(type(None), schemas) == {"nullable": True}
    assert docs_module._schema_for_type(dict, schemas) == {"type": "object"}
    assert docs_module._schema_for_type(DemoModel, schemas)["$ref"] == "#/components/schemas/DemoModel"
    assert docs_module._schema_for_type(DemoData, schemas)["$ref"] == "#/components/schemas/DemoData"
    assert docs_module._schema_for_type(SimpleNamespace, schemas)["$ref"] == "#/components/schemas/SimpleNamespace"
    assert docs_module._schema_for_type(inspect.Signature.empty, schemas) == {}
    assert docs_module._schema_for_type(object(), schemas) == {}
    assert "swagger-ui" in docs_module.get_swagger_ui_html()

    openapi = docs_module.get_openapi(
        "Demo",
        "1.0",
        [
            {
                "path": "/items/{item_id:int}",
                "method": "GET",
                "handler": "get_item",
                "response_model": DemoData,
                "security": ["authenticated"],
                "roles": ["admin"],
                "permissions": ["items:read"],
                "policy": "OwnerPolicy",
                "model": None,
                "deprecated": False,
            }
        ],
    )
    operation = openapi["paths"]["/items/{item_id:int}"]["get"]
    assert operation["x-required-roles"] == ["admin"]
    assert operation["x-authorization-policy"] == "OwnerPolicy"


def test_template_engine_and_jinja_error_path(tmp_path, monkeypatch):
    templates_dir = tmp_path / "templates"
    templates_dir.mkdir()
    (templates_dir / "hello.html").write_text("<h1>${title}</h1>", encoding="utf-8")

    from fusionframe import TemplateEngine

    engine = TemplateEngine(str(templates_dir), globals={"title": "Hi"})
    engine.add_global("name", "Sri")
    assert engine.render("hello.html") == "<h1>Hi</h1>"
    assert engine.render_string("Hello ${name}") == "Hello Sri"
    response = engine.response("hello.html")
    assert response.content_type == "text/html; charset=utf-8"

    import builtins

    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "jinja2":
            raise ImportError("missing")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    from fusionframe.templating import JinjaTemplateEngine

    with pytest.raises(RuntimeError):
        JinjaTemplateEngine(str(templates_dir))


def test_jinja_template_engine_add_global_and_response(tmp_path):
    pytest.importorskip("jinja2")
    templates_dir = tmp_path / "jinja2"
    templates_dir.mkdir()
    (templates_dir / "hello.html").write_text("<h1>{{ title }}</h1>", encoding="utf-8")

    from fusionframe.templating import JinjaTemplateEngine

    engine = JinjaTemplateEngine(str(templates_dir), globals={"title": "Hi"}, autoescape=False)
    engine.add_global("name", "Sri")
    assert engine.render_string("Hello {{ name }}") == "Hello Sri"
    response = engine.response("hello.html")
    assert response.content_type == "text/html; charset=utf-8"
    assert response.render() == b"<h1>Hi</h1>"


def test_cli_failure_paths_and_misc_helpers(monkeypatch, tmp_path):
    runner = CliRunner()
    invalid = runner.invoke(cli, ["run", "example"])
    assert invalid.exit_code != 0
    assert "module:object" in invalid.output

    import fusionframe.cli as cli_module

    monkeypatch.setattr(cli_module.uvicorn, "run", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("boom")))
    failed_run = runner.invoke(cli, ["run", "example:app"])
    assert failed_run.exit_code != 0
    assert "boom" in failed_run.output

    def bad_subprocess(*args, **kwargs):
        raise subprocess.CalledProcessError(1, "benchmark", stderr="bad benchmark")

    monkeypatch.setattr(cli_module.subprocess, "run", bad_subprocess)
    benchmark = runner.invoke(cli, ["benchmark", "--iterations", "5"])
    assert benchmark.exit_code != 0
    assert "bad benchmark" in benchmark.output

    versioned = versioning_module.VersionedAPI(App(), version="2", prefix="/api")
    assert callable(versioned.get("/items"))
    assert callable(versioned.post("/items"))
    assert callable(versioned.put("/items"))
    assert callable(versioned.delete("/items"))
    assert callable(versioned.websocket("/items"))

    http_exc = exceptions_module.HTTPException(418, "teapot", headers={"x-test": "1"})
    ws_exc = exceptions_module.WebSocketException(3001, "bye")
    assert http_exc.status_code == 418
    assert ws_exc.reason == "bye"


def test_session_middleware_store_and_cookie_options():
    app = App()
    store = sessions_module.InMemorySessionStore()
    app.use(
        sessions_module.session_middleware(
            secure=None,
            domain="example.com",
            store=store,
        )
    )

    @app.post("/login")
    async def login(request):
        sessions_module.set_session_value(request, "x", 1)
        return {"ok": True}

    @app.post("/logout")
    async def logout(request):
        sessions_module.logout_user(request)
        return {"ok": True}

    client = TestClient(app)
    login_response = client.post(
        "/login",
        json_body={},
        headers={"x-forwarded-proto": "https"},
    )
    cookie = login_response.headers["set-cookie"].split(";", 1)[0]
    assert "Secure" in login_response.headers["set-cookie"]
    assert "Domain=example.com" in login_response.headers["set-cookie"]

    logout_response = client.post("/logout", json_body={}, headers={"cookie": cookie})
    assert "Max-Age=0" in logout_response.headers["set-cookie"]
