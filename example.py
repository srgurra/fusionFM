from pydantic import BaseModel
from sqlalchemy.orm import Mapped, mapped_column

from fusionFM import (
    AdminPanel,
    App,
    GraphQL,
    Plugin,
    TemplateEngine,
    auth_middleware,
    create_token,
    get_pagination_params,
    mount_static,
    paginate,
    require_role,
    security_headers_middleware,
    session_middleware,
    set_session_user,
    set_session_value,
)
from fusionFM.db import get_db_session
from fusionFM.orm import Model

app = App(title="fusionFM Demo", version="0.3.0")
app.use(session_middleware())
app.use(security_headers_middleware)
app.use(auth_middleware)

templates = TemplateEngine("templates")
mount_static(app, "static")


class DemoPlugin(Plugin):
    def setup(self, app):
        app.state["plugin_loaded"] = True

        @app.get("/plugin-status")
        async def plugin_status(request):
            return {
                "loaded": app.state["plugin_loaded"],
                "started": app.state.get("plugin_started", False),
            }

    async def startup(self, app):
        app.state["plugin_started"] = True

    async def shutdown(self, app):
        app.state["plugin_started"] = False


app.plugin(DemoPlugin)


@app.on_startup
async def warm_framework():
    app.state["ready"] = True


@app.on_shutdown
async def mark_shutdown():
    app.state["ready"] = False


class UserInput(BaseModel):
    name: str
    age: int


class User(Model):
    __tablename__ = "users"

    name: Mapped[str] = mapped_column(nullable=False)
    age: Mapped[int] = mapped_column(nullable=False)


admin = AdminPanel()
admin.register(User)
admin.install(app, get_db_session)


graphql = GraphQL()


@graphql.query("health")
async def health_query(request):
    return {"status": "ok"}


graphql.mount(app)

api_v1 = app.api("1", prefix="/api")


@app.get("/")
async def home(request):
    return templates.response(
        "home.html",
        {
            "title": "fusionFM Demo",
            "feature_count": "routing, docs, auth, sessions, graphql, plugins",
        },
    )


@app.get("/health")
async def health(request):
    return {
        "status": "ok",
        "ready": app.state.get("ready", False),
        "startup_time_ms": app.state.get("startup_time_ms"),
    }


@app.post("/login")
async def login(request):
    role = request.body.get("role", "user")
    token = create_token({"sub": "demo", "roles": [role]})
    set_session_value(request, "user_role", role)
    set_session_user(request, {"sub": "demo", "roles": [role]})
    return {"token": token, "role": role}


@app.get("/admin-only")
@require_role("admin")
async def admin_only(request):
    return {"message": "admin access granted"}


@app.post("/contact")
async def contact(request):
    return {"form": request.form()}


@app.post("/upload")
async def upload(request):
    uploaded = request.files.get("file")
    if not uploaded:
        return {"error": "file is required"}, 400

    return {
        "filename": uploaded.filename,
        "size": uploaded.size,
        "content_type": uploaded.content_type,
    }


@app.websocket("/ws")
async def websocket_echo(socket):
    await socket.accept()
    await socket.send_json({"message": "connected"})

    while not socket.closed:
        data = await socket.receive_json()
        if data is None:
            break
        await socket.send_json({"echo": data})


@app.post("/users", model=UserInput, dependencies={"db": get_db_session})
async def create_user(request, db):
    body = request.body
    user = User(name=body["name"], age=body["age"]).save(db)
    return user.to_dict(), 201


@api_v1.get("/users", dependencies={"db": get_db_session})
async def list_users(request, db):
    users = [user.to_dict() for user in User.all(db)]
    pagination = get_pagination_params(request)
    return paginate(users, **pagination)


@app.get("/users/{id}", dependencies={"db": get_db_session})
async def get_user(request, db):
    user = User.get(db, int(request.params["id"]))
    if not user:
        return {"error": "User not found"}, 404
    return user.to_dict()
