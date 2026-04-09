# fusionframe

`fusionframe` is a lightweight async Python application framework with APIs, sessions, plugins, websockets, admin, migrations, templates, and testing tools built in.

## Docs

- [Getting Started](/Users/srilakshmi/Documents/blogs/fusionFM/docs/getting-started.md)
- [Public API](/Users/srilakshmi/Documents/blogs/fusionFM/docs/public-api.md)
- [Compatibility](/Users/srilakshmi/Documents/blogs/fusionFM/docs/compatibility.md)
- [Auth And Accounts](/Users/srilakshmi/Documents/blogs/fusionFM/docs/auth-accounts.md)
- [Operations](/Users/srilakshmi/Documents/blogs/fusionFM/docs/operations.md)
- [Deployment](/Users/srilakshmi/Documents/blogs/fusionFM/docs/deployment.md)
- [Testing](/Users/srilakshmi/Documents/blogs/fusionFM/docs/testing.md)
- [Releasing](/Users/srilakshmi/Documents/blogs/fusionFM/docs/releasing.md)
- [Full App Workflow](/Users/srilakshmi/Documents/blogs/fusionFM/docs/full-app-workflow.md)
- [Plugin Ecosystem](/Users/srilakshmi/Documents/blogs/fusionFM/docs/plugins.md)
- [fusionframe vs FastAPI](/Users/srilakshmi/Documents/blogs/fusionFM/docs/comparison-fastapi.md)

## Feature Matrix

| Feature | Status | Notes |
| --- | --- | --- |
| Routing | Yes | HTTP routes, path params, websocket routes, path wildcard support |
| Request Handling | Yes | JSON, query params, raw body, form parsing, multipart parsing |
| Data Validation | Yes | Pydantic request model validation |
| Serialization | Yes | JSON and text/HTML response normalization |
| Type Safety | Yes | Typed handlers/models via Python hints + Pydantic |
| Auto API Docs | Yes | OpenAPI JSON + Swagger UI |
| Dependency Injection | Yes | Dependency wrapper with cleanup support |
| ORM | Yes | SQLAlchemy model base helpers |
| Migrations | Yes | Built-in additive SQL migration generator and runner |
| Authentication | Yes | JWT helpers, account helpers, password reset, auth middleware |
| Authorization | Yes | `require_auth`, `require_role`, `require_permission`, resource permissions |
| Admin Panel | Yes | Lightweight HTML admin panel for registered models |
| Middleware Support | Yes | Application middleware stack |
| Session Management | Yes | Signed cookie session middleware |
| Template Engine | Yes | File-based template rendering with `string.Template` |
| Static Files Handling | Yes | Static mount helper |
| WebSockets | Yes | Native ASGI websocket routes |
| Background Tasks | Yes | Post-response background task queue |
| File Uploads | Yes | Multipart file parsing with `UploadedFile` |
| Form Handling | Yes | URL-encoded and multipart form support |
| Pagination | Yes | Pagination helpers |
| Caching | Yes | Redis-backed cache decorator/helpers |
| Rate Limiting | Yes | Redis-backed request rate limiting |
| API Versioning | Yes | Versioned API helper with `/vN` prefixes |
| Testing Support | Yes | Built-in async-free `TestClient` |
| CLI Tools | Yes | Run, migrations, scaffold |
| Project Structure | Yes | CLI scaffold command creates app/templates/static/tests |
| Scalability | Basic | ASGI/async core, Redis cache/rate limit, stateless-friendly helpers, worker-oriented job broker foundation |
| Concurrency Model | Yes | Async ASGI application model |
| Integration with Frontend | Yes | Templates, static mounts, SPA mount helper |
| GraphQL Support | Basic | Lightweight query endpoint/router |
| Microservices Friendly | Basic | Simple JSON service client + async ASGI core |
| Startup Time | Good | Lightweight imports, lifespan hooks, tracked startup timing in `app.state` |
| Security Defaults | Good | Signed sessions, JWT issuer/audience validation, body size limit, CSRF, security headers middleware |

## Install

```bash
pip install fusionframe
```

## Quick Start

```python
from pydantic import BaseModel
from fusionframe import App

app = App()


class UserInput(BaseModel):
    name: str


@app.get("/")
async def home(request):
    return {"message": "hello"}


@app.post("/users", model=UserInput)
async def create_user(request):
    return {"user": request.body}, 201
```

For local development:

```bash
pip install -e .[dev]
fusionframe run example:app
```

## Why fusionframe

`fusionframe` is aiming to be stronger than API-first frameworks for app-style backends by giving you:

- sessions and auth
- admin
- migrations
- templates and static files
- GraphQL and REST in one app
- jobs and lifecycle hooks
- plugin-based extensibility

See the full-stack reference example at [examples/saas_app.py](/Users/srilakshmi/Documents/blogs/fusionFM/examples/saas_app.py).

## Core APIs

### Versioned API

```python
api_v1 = app.api("1", prefix="/api")

@api_v1.get("/users")
async def users(request):
    return {"items": []}
```

### Sessions

```python
from fusionframe import session_middleware, set_session_value

app.use(session_middleware())

@app.post("/login")
async def login(request):
    set_session_value(request, "user_id", "123")
    return {"ok": True}
```

### Security Hardening

```python
from fusionframe import security_headers_middleware

app = App(max_body_size=1024 * 1024)
app.use(security_headers_middleware)
```

Session cookies are signed and expiring. JWT verification also checks issuer, and audience when configured.

### Authorization

```python
from fusionframe import require_role

@app.get("/admin")
@require_role("admin")
async def admin(request):
    return {"ok": True}
```

### Accounts

```python
from fusionframe import AccountManager, InMemoryAuthBackend

backend = InMemoryAuthBackend()
accounts = AccountManager(backend)
```

### Templates and Static Files

```python
from fusionframe import TemplateEngine, mount_static

templates = TemplateEngine("templates")
mount_static(app, "static")

@app.get("/")
async def home(request):
    return templates.response("home.html", {"title": "fusionframe"})
```

### Forms and Uploads

```python
@app.post("/contact")
async def contact(request):
    return {"form": request.form()}

@app.post("/upload")
async def upload(request):
    file = request.files["file"]
    return {"filename": file.filename, "size": file.size}
```

### Pagination

```python
from fusionframe import get_pagination_params, paginate

@app.get("/items")
async def items(request):
    params = get_pagination_params(request)
    return paginate(list(range(100)), **params)
```

### Admin Panel

```python
from fusionframe import AdminPanel
from fusionframe.db import get_db_session

admin = AdminPanel()
admin.register(User)
admin.install(app, get_db_session)
```

### GraphQL

```python
from fusionframe import GraphQL

graphql = GraphQL()

@graphql.query("health")
async def health(request):
    return {"status": "ok"}

graphql.mount(app)
```

### Lifecycle Hooks And Startup Timing

```python
@app.on_startup
async def warmup():
    app.state["ready"] = True

@app.get("/health")
async def health(request):
    return {"startup_time_ms": app.state["startup_time_ms"]}
```

### Frontend Integration

```python
from fusionframe import mount_spa

mount_spa(app, "frontend", mount_path="/app")
```

### Testing

```python
from fusionframe import TestClient

client = TestClient(app)
response = client.get("/")
assert response.status_code == 200
```

## CLI

```bash
fusionframe run example:app
fusionframe migrations-init
fusionframe makemigration example:app -m "create users"
fusionframe migrate
fusionframe scaffold myproject
fusionframe benchmark --iterations 5000
```

## Notes

- GraphQL support is intentionally lightweight and currently targets simple query dispatch.
- Migrations currently support additive changes like creating tables and adding columns.
- Scalability and microservice support are practical building blocks, not a full orchestration stack.
- Startup remains fast because initialization is small by default, and startup duration is recorded when lifespan startup runs.
