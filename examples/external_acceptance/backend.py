from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel

from fusionframe import (
    App,
    GraphQL,
    HTTPException,
    ServiceClient,
    TemplateEngine,
    WebSocketException,
    auth_middleware,
    cors_middleware,
    csrf_middleware,
    get_csrf_token,
    get_pagination_params,
    login_user,
    mount_spa,
    mount_static,
    paginate,
    require_auth,
    require_permission,
    security_headers_middleware,
    session_middleware,
)


ROOT = Path(__file__).parent


class Credentials(BaseModel):
    email: str
    password: str


class VerificationPayload(BaseModel):
    token: str


class InsightRequest(BaseModel):
    owner: str = "encode"
    repo: str = "starlette"
    package: str = "fastapi"
    topic: str = "python web framework"


class ExternalOpenSourceAPIs:
    """Small adapter around public APIs; tests replace this with a fake."""

    def __init__(self):
        self.github = ServiceClient("https://api.github.com", timeout=8)
        self.pypi = ServiceClient("https://pypi.org/pypi", timeout=8)
        self.news = ServiceClient("https://hn.algolia.com/api/v1", timeout=8)

    def github_repo(self, owner: str, repo: str):
        return self.github.get(f"/repos/{owner}/{repo}")

    def pypi_package(self, package: str):
        return self.pypi.get(f"/{package}/json")

    def hacker_news(self, topic: str):
        return self.news.get("/search", headers=None) if not topic else self.news.get(f"/search?query={topic}")


class DemoAccounts:
    def __init__(self):
        self.users = {
            "demo@example.com": {
                "password": "demo-password",
                "verified": True,
                "identity": {
                    "sub": "demo@example.com",
                    "roles": ["developer"],
                    "permissions": ["external:read", "jobs:write"],
                },
            }
        }
        self._verification_tokens = {}

    def register(self, email: str, password: str):
        token = f"verify-{email}"
        self.users[email] = {
            "password": password,
            "verified": False,
            "identity": {
                "sub": email,
                "roles": ["developer"],
                "permissions": ["external:read"],
            },
        }
        self._verification_tokens[token] = email
        return token

    def verify(self, token: str):
        email = self._verification_tokens.get(token)
        if not email or email not in self.users:
            return False
        self.users[email]["verified"] = True
        return True

    def authenticate(self, email: str, password: str):
        user = self.users.get(email)
        if not user or user["password"] != password or not user["verified"]:
            return None
        return dict(user["identity"])


def create_app(external_apis=None, accounts=None):
    app = App(title="fusionframe External Acceptance App", version="0.1.0")
    app.state.external_apis = external_apis or ExternalOpenSourceAPIs()
    app.state.accounts = accounts or DemoAccounts()
    app.state.refreshes = []

    app.use(
        cors_middleware(
            allow_origins=["http://localhost:5173"],
            allow_credentials=True,
        )
    )
    app.use(session_middleware(secure=False))
    app.use(
        csrf_middleware(
            exempt_paths={
                "/api/register",
                "/api/verify",
                "/api/login",
                "/api/health",
            }
        )
    )
    app.use(auth_middleware)
    app.use(security_headers_middleware)

    templates = TemplateEngine(str(ROOT / "templates"))
    mount_static(app, str(ROOT / "static"), url_path="/assets")
    mount_spa(app, str(ROOT / "frontend" / "dist"), mount_path="/client")

    api_v1 = app.api("1", prefix="/api")
    graphql = GraphQL()

    @app.get("/")
    async def homepage(request):
        return templates.response(
            "dashboard.html",
            {"title": "fusionframe External Acceptance"},
        )

    @app.get("/api/health")
    async def health(request):
        return {
            "status": "ok",
            "features": [
                "sessions",
                "csrf",
                "auth",
                "external-apis",
                "graphql",
                "websockets",
                "jobs",
                "react",
            ],
        }

    @app.post("/api/register", model=Credentials)
    async def register(request):
        token = request.app.state.accounts.register(
            request.body["email"],
            request.body["password"],
        )
        return {"verification_token": token}, 201

    @app.post("/api/verify", model=VerificationPayload)
    async def verify(request):
        if not request.app.state.accounts.verify(request.body["token"]):
            raise HTTPException(400, "Invalid verification token")
        return {"verified": True}

    @app.post("/api/login", model=Credentials)
    async def login(request):
        identity = request.app.state.accounts.authenticate(
            request.body["email"],
            request.body["password"],
        )
        if identity is None:
            raise HTTPException(401, "Invalid credentials")
        login_user(request, identity)
        return {"user": identity, "csrf": get_csrf_token(request)}

    @app.get("/api/me")
    @require_auth
    async def me(request):
        return {"user": request.user, "csrf": get_csrf_token(request)}

    @api_v1.get("/feed")
    @require_permission("external:read")
    async def feed(request):
        params = get_pagination_params(request, default_per_page=2, max_per_page=5)
        topic = request.query.get("topic", ["python web framework"])[0]
        news = _normalize_news(request.app.state.external_apis.hacker_news(topic))
        return paginate(news, **params)

    @app.post("/api/insights", model=InsightRequest)
    @require_permission("external:read")
    async def insights(request):
        return _build_insight_response(request.app.state.external_apis, request.body)

    @app.post("/api/feedback", request_media_type="application/x-www-form-urlencoded")
    @require_auth
    async def feedback(request):
        return {
            "received": True,
            "message": request.form().get("message"),
            "user": request.user["sub"],
        }

    @app.post("/api/upload")
    @require_auth
    async def upload(request):
        if "artifact" not in request.files:
            raise HTTPException(400, "artifact file is required")
        file = request.files["artifact"]
        return {
            "filename": file.filename,
            "content_type": file.content_type,
            "size": file.size,
        }

    @app.post("/api/background")
    @require_auth
    async def background(request):
        def remember(value):
            request.app.state.refreshes.append(value)

        request.background.add_task(remember, "background-complete")
        return {"queued": True}

    @app.post("/api/jobs/refresh", model=InsightRequest)
    @require_permission("jobs:write")
    async def refresh_job(request):
        async def refresh(payload):
            result = _build_insight_response(request.app.state.external_apis, payload)
            request.app.state.refreshes.append(result["summary"])
            return result

        job_id = await request.app.jobs.enqueue(
            refresh,
            request.body,
            name="external-insight-refresh",
            timeout=2,
        )
        return {"job_id": job_id}, 202

    @graphql.query("stats")
    async def stats(request):
        return {
            "refreshes": len(request.app.state.refreshes),
            "framework": "fusionframe",
        }

    graphql.mount(app, path="/api/graphql")

    @app.websocket("/ws/insights")
    async def insight_socket(socket):
        await socket.accept()
        payload = await socket.receive_json()
        if not payload:
            raise WebSocketException(1003, "Expected JSON payload")
        await socket.send_json(_build_insight_response(app.state.external_apis, payload))

    return app


def _build_insight_response(external_apis, payload):
    repo = external_apis.github_repo(payload["owner"], payload["repo"])
    package = external_apis.pypi_package(payload["package"])
    news = _normalize_news(external_apis.hacker_news(payload["topic"]))

    stars = int(repo.get("stargazers_count", 0) or 0)
    downloads_proxy = len(news) * 100
    score = min(100, stars // 1000 + downloads_proxy // 100)

    return {
        "summary": f"{repo.get('full_name')} + {package.get('info', {}).get('name')}",
        "repo": {
            "name": repo.get("full_name"),
            "stars": stars,
            "language": repo.get("language"),
            "license": (repo.get("license") or {}).get("spdx_id"),
        },
        "package": {
            "name": package.get("info", {}).get("name"),
            "version": package.get("info", {}).get("version"),
            "summary": package.get("info", {}).get("summary"),
        },
        "news": news[:5],
        "score": score,
    }


def _normalize_news(payload):
    hits = payload.get("hits", []) if isinstance(payload, dict) else []
    return [
        {
            "title": hit.get("title") or hit.get("story_title") or "Untitled",
            "url": hit.get("url") or hit.get("story_url"),
            "points": hit.get("points") or 0,
        }
        for hit in hits
    ]


app = create_app()
