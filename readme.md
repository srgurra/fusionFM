# fusionFM

`fusionFM` is a lightweight async Python web framework with routing, validation, ORM support, websockets, plugins, and a growing set of batteries-included helpers.

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
| Authentication | Yes | JWT helpers + auth middleware |
| Authorization | Yes | `require_auth`, `require_role`, `require_permission` |
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
| Scalability | Basic | ASGI/async core, Redis cache/rate limit, stateless-friendly helpers |
| Concurrency Model | Yes | Async ASGI application model |
| Integration with Frontend | Yes | Templates, static mounts, SPA mount helper |
| GraphQL Support | Basic | Lightweight query endpoint/router |
| Microservices Friendly | Basic | Simple JSON service client + async ASGI core |
| Startup Time | Good | Lightweight imports, lifespan hooks, tracked startup timing in `app.state` |
| Security Defaults | Basic | Signed sessions, JWT issuer/audience validation, body size limit, security headers middleware |

## Install

```bash
pip install -e .
```

## Quick Start

```python
from pydantic import BaseModel
from fusionFM import App

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

Run:

```bash
fusionfm run example:app
```

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
from fusionFM import session_middleware, set_session_value

app.use(session_middleware())

@app.post("/login")
async def login(request):
    set_session_value(request, "user_id", "123")
    return {"ok": True}
```

### Security Hardening

```python
from fusionFM import security_headers_middleware

app = App(max_body_size=1024 * 1024)
app.use(security_headers_middleware)
```

Session cookies are signed and expiring. JWT verification also checks issuer, and audience when configured.

### Authorization

```python
from fusionFM import require_role

@app.get("/admin")
@require_role("admin")
async def admin(request):
    return {"ok": True}
```

### Templates and Static Files

```python
from fusionFM import TemplateEngine, mount_static

templates = TemplateEngine("templates")
mount_static(app, "static")

@app.get("/")
async def home(request):
    return templates.response("home.html", {"title": "fusionFM"})
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
from fusionFM import get_pagination_params, paginate

@app.get("/items")
async def items(request):
    params = get_pagination_params(request)
    return paginate(list(range(100)), **params)
```

### Admin Panel

```python
from fusionFM import AdminPanel
from fusionFM.db import get_db_session

admin = AdminPanel()
admin.register(User)
admin.install(app, get_db_session)
```

### GraphQL

```python
from fusionFM import GraphQL

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
from fusionFM import mount_spa

mount_spa(app, "frontend", mount_path="/app")
```

### Testing

```python
from fusionFM import TestClient

client = TestClient(app)
response = client.get("/")
assert response.status_code == 200
```

## CLI

```bash
fusionfm run example:app
fusionfm migrations-init
fusionfm makemigration example:app -m "create users"
fusionfm migrate
fusionfm scaffold myproject
```

## Notes

- GraphQL support is intentionally lightweight and currently targets simple query dispatch.
- Migrations currently support additive changes like creating tables and adding columns.
- Scalability and microservice support are practical building blocks, not a full orchestration stack.
- Startup remains fast because initialization is small by default, and startup duration is recorded when lifespan startup runs.
