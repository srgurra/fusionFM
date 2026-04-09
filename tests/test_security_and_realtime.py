import asyncio

from fusionframe import (
    AccountManager,
    App,
    AuthorizationPolicy,
    build_permission,
    cors_middleware,
    InMemoryAuthBackend,
    Identity,
    PasswordHasher,
    PasswordResetManager,
    PolicyRegistry,
    TestClient,
    auth_middleware,
    authenticate_with,
    authorize,
    csrf_middleware,
    evaluate_policy,
    get_csrf_token,
    has_permission,
    has_role,
    login_user,
    logout_user,
    create_token,
    has_resource_permission,
    require_policy,
    require_resource_permission,
    rotate_session,
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


def test_identity_helpers_and_logout():
    identity = Identity(subject="u1", roles=["admin"], permissions=["write"])
    assert has_role(identity, "admin") is True
    assert has_permission(identity, "write") is True
    assert authorize(identity, roles=["admin"], permissions=["write"]) is True

    app = App(max_body_size=128)
    app.use(session_middleware(secure=False))
    app.use(auth_middleware)

    @app.post("/login")
    async def login(request):
        login_user(request, identity)
        return {"ok": True}

    @app.post("/logout")
    async def logout(request):
        logout_user(request)
        return {"ok": True}

    client = TestClient(app)
    login_response = client.post("/login", json_body={})
    cookie = login_response.headers["set-cookie"].split(";", 1)[0]
    logout_response = client.post("/logout", json_body={}, headers={"cookie": cookie})
    assert logout_response.status_code == 200
    assert "Max-Age=0" in logout_response.headers["set-cookie"]


def test_csrf_middleware_and_session_rotation():
    app = App(max_body_size=128)
    app.use(session_middleware(secure=False))
    app.use(csrf_middleware(exempt_paths={"/login"}))
    app.use(auth_middleware)

    @app.get("/form")
    async def form(request):
        return {"csrf": get_csrf_token(request)}

    @app.post("/login")
    async def login(request):
        before = request.session.get("_csrf_token")
        login_user(request, {"sub": "user-1"})
        after = request.session.get("_csrf_token")
        return {"rotated": before != after}

    @app.post("/submit")
    async def submit(request):
        return {"ok": True}

    client = TestClient(app)
    form_response = client.get("/form")
    cookie = form_response.headers["set-cookie"].split(";", 1)[0]
    csrf = form_response.json()["csrf"]

    rejected = client.post("/submit", json_body={}, headers={"cookie": cookie})
    assert rejected.status_code == 403

    accepted = client.post(
        "/submit",
        json_body={},
        headers={"cookie": cookie, "x-csrf-token": csrf},
    )
    assert accepted.status_code == 200

    login_response = client.post("/login", json_body={}, headers={"cookie": cookie})
    assert login_response.status_code == 200
    assert login_response.json()["rotated"] is True


def test_password_hasher_and_auth_backend():
    hasher = PasswordHasher()
    encoded = hasher.hash("secret")
    assert hasher.verify("secret", encoded) is True
    assert hasher.verify("wrong", encoded) is False

    backend = InMemoryAuthBackend(hasher=hasher)
    backend.register(
        "sri@example.com",
        "secret",
        identity={"sub": "user-1", "roles": ["admin"], "permissions": ["tickets:write"]},
    )

    authenticated = asyncio.run(
        authenticate_with(backend, "sri@example.com", "secret")
    )
    rejected = asyncio.run(
        authenticate_with(backend, "sri@example.com", "wrong")
    )

    assert authenticated["sub"] == "user-1"
    assert authenticated["roles"] == ["admin"]
    assert rejected is None


def test_password_reset_manager_and_backend_password_update():
    backend = InMemoryAuthBackend()
    backend.register("sri@example.com", "secret", identity={"sub": "user-1"})
    resets = PasswordResetManager()
    token = resets.issue_token("sri@example.com", expires_in=300)

    changed = asyncio.run(
        resets.reset_password(backend, "sri@example.com", token, "new-secret")
    )
    authenticated = asyncio.run(
        authenticate_with(backend, "sri@example.com", "new-secret")
    )
    rejected = asyncio.run(
        authenticate_with(backend, "sri@example.com", "secret")
    )

    assert changed is True
    assert authenticated["sub"] == "user-1"
    assert rejected is None


def test_account_manager_registration_verification_and_password_change():
    backend = InMemoryAuthBackend()
    accounts = AccountManager(backend)

    registered = asyncio.run(
        accounts.register(
            "owner@example.com",
            "secret",
            identity={"sub": "owner-1", "roles": ["owner"]},
        )
    )
    pre_verify = asyncio.run(
        accounts.authenticate("owner@example.com", "secret", require_verified=True)
    )
    token = accounts.issue_verification_token("owner@example.com", expires_in=300)
    marked = asyncio.run(accounts.mark_verified(token))
    post_verify = asyncio.run(
        accounts.authenticate("owner@example.com", "secret", require_verified=True)
    )
    changed = asyncio.run(
        accounts.change_password("owner@example.com", "secret", "new-secret")
    )
    changed_login = asyncio.run(
        accounts.authenticate("owner@example.com", "new-secret", require_verified=True)
    )

    assert registered.identifier == "owner@example.com"
    assert pre_verify is None
    assert marked is True
    assert post_verify["sub"] == "owner-1"
    assert changed is True
    assert changed_login["sub"] == "owner-1"


def test_resource_permissions_and_decorator():
    assert has_resource_permission(
        {"permissions": [build_permission("projects", "write")]},
        "projects",
        "write",
    )
    assert has_resource_permission(
        {"permissions": [build_permission("projects", "*")]},
        "projects",
        "write",
    )

    app = App()
    app.use(session_middleware(secure=False))
    app.use(auth_middleware)

    @app.post("/login")
    async def login(request):
        login_user(
            request,
            {"sub": "user-1", "permissions": [build_permission("projects", "read")]},
        )
        return {"ok": True}

    @app.get("/projects/{resource}")
    @require_resource_permission("read", lambda request: request.params["resource"])
    async def project_detail(request):
        return {"ok": True}

    client = TestClient(app)
    login_response = client.post("/login", json_body={})
    cookie = login_response.headers["set-cookie"].split(";", 1)[0]

    allowed = client.get("/projects/projects", headers={"cookie": cookie})
    denied = client.get("/projects/tickets", headers={"cookie": cookie})

    assert allowed.status_code == 200
    assert denied.status_code == 403


def test_policy_registry_and_require_policy():
    registry = PolicyRegistry()

    class AdminPolicy(AuthorizationPolicy):
        async def authorize(self, request, user):
            return has_role(user, "admin")

    registry.register("admin_only", AdminPolicy())
    app = App()
    app.use(session_middleware(secure=False))
    app.use(auth_middleware)

    @app.post("/login")
    async def login(request):
        login_user(request, {"sub": "admin", "roles": ["admin"]})
        return {"ok": True}

    @app.get("/secure")
    @require_policy(registry.get("admin_only"))
    async def secure(request):
        return {"ok": True}

    client = TestClient(app)
    denied = client.get("/secure")
    assert denied.status_code == 403

    login_response = client.post("/login", json_body={})
    cookie = login_response.headers["set-cookie"].split(";", 1)[0]
    allowed = client.get("/secure", headers={"cookie": cookie})
    assert allowed.status_code == 200

    result = asyncio.run(
        evaluate_policy(registry.get("admin_only"), None, {"roles": ["admin"]})
    )
    assert result is True


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


def test_websocket_uses_session_auth_middleware():
    app = App()
    app.use(session_middleware(secure=False))
    app.use(auth_middleware)

    @app.post("/login")
    async def login(request):
        login_user(request, {"sub": "ws-user", "roles": ["member"]})
        return {"ok": True}

    @app.websocket("/ws/session")
    async def socket_handler(socket):
        await socket.accept()
        await socket.send_json({"user": socket.user})

    client = TestClient(app)
    login_response = client.post("/login", json_body={})
    cookie = login_response.headers["set-cookie"].split(";", 1)[0]

    messages = [
        {"type": "websocket.connect"},
        {"type": "websocket.disconnect", "code": 1000},
    ]
    sent = []

    async def receive():
        return messages.pop(0)

    async def send(message):
        sent.append(message)

    asyncio.run(
        app(
            {
                "type": "websocket",
                "path": "/ws/session",
                "query_string": b"",
                "headers": [(b"cookie", cookie.encode("utf-8"))],
            },
            receive,
            send,
        )
    )

    assert sent[0]["type"] == "websocket.accept"
    assert '"sub": "ws-user"' in sent[1]["text"]


def test_websocket_prefers_bearer_auth_over_session():
    app = App()
    app.use(session_middleware(secure=False))
    app.use(auth_middleware)

    @app.post("/login")
    async def login(request):
        login_user(request, {"sub": "session-user", "roles": ["member"]})
        return {"ok": True}

    @app.websocket("/ws/auth")
    async def socket_handler(socket):
        await socket.accept()
        await socket.send_json({"user": socket.user})

    client = TestClient(app)
    login_response = client.post("/login", json_body={})
    cookie = login_response.headers["set-cookie"].split(";", 1)[0]
    bearer = create_token({"sub": "bearer-user", "roles": ["admin"]})

    messages = [
        {"type": "websocket.connect"},
        {"type": "websocket.disconnect", "code": 1000},
    ]
    sent = []

    async def receive():
        return messages.pop(0)

    async def send(message):
        sent.append(message)

    asyncio.run(
        app(
            {
                "type": "websocket",
                "path": "/ws/auth",
                "query_string": b"",
                "headers": [
                    (b"cookie", cookie.encode("utf-8")),
                    (b"authorization", f"Bearer {bearer}".encode("utf-8")),
                ],
            },
            receive,
            send,
        )
    )

    assert '"sub": "bearer-user"' in sent[1]["text"]


def test_cors_middleware_handles_simple_and_preflight_requests():
    app = App()
    app.use(
        cors_middleware(
            allow_origins=["http://localhost:5173"],
            allow_credentials=True,
        )
    )

    @app.get("/data")
    async def data(request):
        return {"ok": True}

    client = TestClient(app)

    simple = client.get(
        "/data",
        headers={"origin": "http://localhost:5173"},
    )
    preflight = client.request(
        "OPTIONS",
        "/data",
        headers={
            "origin": "http://localhost:5173",
            "access-control-request-method": "GET",
        },
    )

    assert simple.status_code == 200
    assert simple.headers["access-control-allow-origin"] == "http://localhost:5173"
    assert simple.headers["access-control-allow-credentials"] == "true"
    assert preflight.status_code == 204
    assert preflight.headers["access-control-allow-methods"]
