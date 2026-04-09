import asyncio
import importlib
import types

cache_module = importlib.import_module("fusionframe.cache")
plugins_module = importlib.import_module("fusionframe.plugins")
rate_limit_module = importlib.import_module("fusionframe.rate_limit")
services_module = importlib.import_module("fusionframe.services")


class DummyRequest:
    def __init__(self):
        self.path = "/items"
        self.params = {"item_id": "1"}
        self.query = {"page": ["1"]}
        self.body = {"active": True}
        self.headers = {}
        self.scope = {}


def test_cache_helpers_and_decorator(monkeypatch):
    store = {}

    class FakeRedis:
        def get(self, key):
            return store.get(key)

        def set(self, key, value, ex=None):
            store[key] = value

        def delete(self, key):
            store.pop(key, None)

    monkeypatch.setattr(cache_module, "r", FakeRedis())

    request = DummyRequest()
    key = cache_module.build_cache_key(request, prefix="items")
    assert key.startswith("items:")

    cache_module.cache_set("x", {"ok": True}, ttl=10)
    assert cache_module.cache_get("x") == {"ok": True}
    cache_module.cache_delete("x")
    assert cache_module.cache_get("x") is None

    calls = {"count": 0}

    @cache_module.cache(ttl=10, key_prefix="demo")
    async def handler(request):
        calls["count"] += 1
        return {"value": calls["count"]}

    first = asyncio.run(handler(request))
    second = asyncio.run(handler(request))

    assert first == {"value": 1}
    assert second == {"value": 1}
    assert calls["count"] == 1

    class BrokenRedis:
        def get(self, key):
            raise RuntimeError("down")

        def set(self, key, value, ex=None):
            raise RuntimeError("down")

        def delete(self, key):
            raise RuntimeError("down")

    monkeypatch.setattr(cache_module, "r", BrokenRedis())
    assert cache_module.cache_get("missing") is None
    cache_module.cache_set("x", {"ok": True}, ttl=1)
    cache_module.cache_delete("x")


def test_rate_limit_helper_and_decorator(monkeypatch):
    state = {}

    class FakeRedis:
        def incr(self, key):
            state[key] = state.get(key, 0) + 1
            return state[key]

        def expire(self, key, per):
            return True

    monkeypatch.setattr(rate_limit_module, "r", FakeRedis())

    request = DummyRequest()
    request.headers = {"x-forwarded-for": "10.0.0.1, 10.0.0.2"}
    assert rate_limit_module._client_ip(request) == "10.0.0.1"

    @rate_limit_module.rate_limit(1, per=60, key_prefix="items")
    async def handler(request):
        return {"ok": True}

    allowed = asyncio.run(handler(request))
    blocked = asyncio.run(handler(request))

    assert allowed == {"ok": True}
    assert blocked[1] == 429
    assert blocked[0]["error"] == "Rate limit exceeded"

    class BrokenRedis:
        def incr(self, key):
            raise RuntimeError("down")

        def expire(self, key, per):
            raise RuntimeError("down")

    monkeypatch.setattr(rate_limit_module, "r", BrokenRedis())

    @rate_limit_module.rate_limit(1, per=60, key_prefix="fallback")
    async def fallback(request):
        return {"fallback": True}

    request.headers = {}
    request.scope = {"client": ("127.0.0.1", 1234)}
    assert asyncio.run(fallback(request)) == {"fallback": True}
    request.scope = {}
    assert rate_limit_module._client_ip(request) == "unknown"


def test_service_client_json_and_bytes(monkeypatch):
    captured = {}

    class FakeHeaders(dict):
        def get(self, key, default=None):
            return super().get(key, default)

    class FakeResponse:
        def __init__(self, body, content_type):
            self._body = body
            self.headers = FakeHeaders({"Content-Type": content_type})

        def read(self):
            return self._body

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    def fake_urlopen(request, timeout):
        captured["method"] = request.get_method()
        captured["url"] = request.full_url
        captured["headers"] = dict(request.header_items())
        captured["timeout"] = timeout
        if request.data:
            return FakeResponse(b'{"ok": true}', "application/json")
        return FakeResponse(b"plain-bytes", "application/octet-stream")

    monkeypatch.setattr(services_module, "urlopen", fake_urlopen)

    client = services_module.ServiceClient("https://api.example.com", timeout=3)
    assert client.get("/health") == b"plain-bytes"
    response = client.post("/items", json_body={"name": "Widget"})

    assert response == {"ok": True}
    assert captured["method"] == "POST"
    assert captured["url"] == "https://api.example.com/items"
    assert captured["timeout"] == 3


def test_plugin_loader_from_class_instance_and_path(monkeypatch):
    class DemoPlugin(plugins_module.Plugin):
        def setup(self, app):
            return None

    loaded_class = plugins_module.load_plugin(DemoPlugin)
    loaded_instance = plugins_module.load_plugin(DemoPlugin())

    module = types.SimpleNamespace(plugin=DemoPlugin)
    monkeypatch.setattr(plugins_module.importlib, "import_module", lambda name: module)
    loaded_path = plugins_module.load_plugin("demo.module")

    assert isinstance(loaded_class, DemoPlugin)
    assert isinstance(loaded_instance, DemoPlugin)
    assert isinstance(loaded_path, DemoPlugin)

    class InvalidPlugin:
        pass

    try:
        plugins_module.load_plugin(InvalidPlugin())
    except TypeError as exc:
        assert "setup(app)" in str(exc)
    else:
        raise AssertionError("expected invalid plugin type error")

    monkeypatch.setattr(
        plugins_module.importlib,
        "import_module",
        lambda name: types.SimpleNamespace(),
    )
    try:
        plugins_module.load_plugin("broken.module:missing")
    except ImportError as exc:
        assert "could not be loaded" in str(exc)
    else:
        raise AssertionError("expected import error")
