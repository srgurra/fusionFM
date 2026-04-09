from pydantic import BaseModel
from sqlalchemy.orm import Mapped, mapped_column

from fusionframe import (
    AdminPanel,
    App,
    GraphQL,
    TemplateEngine,
    auth_middleware,
    login_user,
    mount_spa,
    mount_static,
    require_role,
    security_headers_middleware,
    session_middleware,
)
from fusionframe.db import get_db_session
from fusionframe.orm import Model


app = App(title="fusionframe SaaS Example", version="0.1.0")
app.use(session_middleware(secure=False))
app.use(security_headers_middleware)
app.use(auth_middleware)

templates = TemplateEngine("templates", globals={"app_name": "fusionframe SaaS"})
mount_static(app, "static")
mount_spa(app, "frontend", mount_path="/app")


class TenantCreate(BaseModel):
    name: str
    slug: str


class TicketCreate(BaseModel):
    title: str
    status: str = "open"


class Tenant(Model):
    __tablename__ = "saas_tenants"

    name: Mapped[str] = mapped_column(nullable=False)
    slug: Mapped[str] = mapped_column(nullable=False, unique=True)


class Ticket(Model):
    __tablename__ = "saas_tickets"

    title: Mapped[str] = mapped_column(nullable=False)
    status: Mapped[str] = mapped_column(nullable=False, default="open")


@app.on_startup
async def mark_ready():
    app.state.ready = True


@app.get("/")
async def landing(request):
    return templates.response(
        "home.html",
        {"title": "fusionframe SaaS", "feature_count": "auth, admin, graphql, spa, jobs"},
    )


@app.post("/login")
async def login(request):
    role = request.body.get("role", "member")
    login_user(
        request,
        {
            "sub": "demo-user",
            "roles": [role],
            "permissions": ["tickets:read", "tickets:write"],
        },
    )
    return {"ok": True, "role": role}


@app.get("/health")
async def health(request):
    return {
        "status": "ok",
        "ready": app.state.get("ready", False),
        "startup_time_ms": app.state.get("startup_time_ms"),
    }


api = app.api("1", prefix="/api")


@api.post("/tenants", model=TenantCreate, dependencies={"db": get_db_session})
@require_role("admin")
async def create_tenant(request, db):
    tenant = Tenant(**request.body).save(db)
    return tenant.to_dict(), 201


@api.get("/tenants", dependencies={"db": get_db_session})
async def list_tenants(request, db):
    return {"items": [tenant.to_dict() for tenant in Tenant.all(db)]}


@api.post("/tickets", model=TicketCreate, dependencies={"db": get_db_session})
async def create_ticket(request, db):
    ticket = Ticket(**request.body).save(db)
    return ticket.to_dict(), 201


@api.get("/tickets", dependencies={"db": get_db_session})
async def list_tickets(request, db):
    return {"items": [ticket.to_dict() for ticket in Ticket.all(db)]}


graphql = GraphQL()


@graphql.query("health")
async def graphql_health(request):
    return {"ready": app.state.get("ready", False)}


graphql.mount(app)


admin = AdminPanel(roles=["admin"])
admin.register(Tenant, label="Tenants", list_display=["id", "name", "slug"])
admin.register(Ticket, label="Tickets", list_display=["id", "title", "status"])
admin.install(app, get_db_session)


@app.jobs.schedule(30, name="sync_metrics")
async def sync_metrics():
    app.state.last_metrics_sync = "ok"
