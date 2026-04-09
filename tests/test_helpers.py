from pathlib import Path

from fusionFM import (
    App,
    GraphQL,
    TemplateEngine,
    TestClient,
    get_pagination_params,
    mount_spa,
    mount_static,
    paginate,
)


def test_templates_static_forms_uploads_and_versioning(tmp_path):
    templates_dir = tmp_path / "templates"
    static_dir = tmp_path / "static"
    templates_dir.mkdir()
    static_dir.mkdir()
    (templates_dir / "home.html").write_text("<h1>${title}</h1>", encoding="utf-8")
    (static_dir / "site.css").write_text("body{}", encoding="utf-8")

    app = App()
    templates = TemplateEngine(str(templates_dir))
    mount_static(app, str(static_dir))
    api_v1 = app.api("1", prefix="/api")

    @app.get("/")
    async def home(request):
        return templates.response("home.html", {"title": "Home"})

    @app.post("/contact")
    async def contact(request):
        return {"form": request.form()}

    @app.post("/upload")
    async def upload(request):
        file = request.files["file"]
        return {"filename": file.filename, "size": file.size}

    @api_v1.get("/items")
    async def items(request):
        return paginate(list(range(5)), **get_pagination_params(request, default_per_page=2))

    client = TestClient(app)

    home_response = client.get("/")
    assert home_response.status_code == 200
    assert home_response.text == "<h1>Home</h1>"

    static_response = client.get("/static/site.css")
    assert static_response.status_code == 200
    assert static_response.text == "body{}"

    form_response = client.post("/contact", form={"name": "Sri"})
    assert form_response.json()["form"] == {"name": "Sri"}

    boundary = "----fusionfm"
    body = (
        f"--{boundary}\r\n"
        'Content-Disposition: form-data; name="file"; filename="hello.txt"\r\n'
        "Content-Type: text/plain\r\n\r\n"
        "hello world\r\n"
        f"--{boundary}--\r\n"
    ).encode("utf-8")

    # override TestClient payload for multipart by calling the internal async path directly
    sent = []
    messages = [{"type": "http.request", "body": body, "more_body": False}]

    async def receive():
        return messages.pop(0)

    async def send(message):
        sent.append(message)

    import asyncio

    asyncio.run(
        app(
            {
                "type": "http",
                "method": "POST",
                "path": "/upload",
                "query_string": b"",
                "headers": [(b"content-type", f"multipart/form-data; boundary={boundary}".encode("utf-8"))],
            },
            receive,
            send,
        )
    )
    assert b"hello.txt" in sent[-1]["body"]

    items_response = client.get("/api/v1/items", query={"page": 2, "per_page": 2})
    assert items_response.json()["items"] == [2, 3]


def test_graphql_and_spa_mount(tmp_path):
    spa_root = tmp_path / "frontend"
    spa_root.mkdir()
    (spa_root / "index.html").write_text("<div>spa</div>", encoding="utf-8")

    app = App()
    graphql = GraphQL()

    @graphql.query("ping")
    def ping(request):
        return {"pong": True}

    graphql.mount(app)
    mount_spa(app, str(spa_root), mount_path="/app")

    client = TestClient(app)

    graphql_response = client.post("/graphql", json_body={"query": "{ ping }"})
    assert graphql_response.status_code == 200
    assert graphql_response.json()["data"]["ping"] == {"pong": True}

    graphql_index = client.get("/graphql")
    assert graphql_index.status_code == 200
    assert "ping" in graphql_index.text

    spa_response = client.get("/app")
    assert spa_response.status_code == 200
    assert spa_response.text == "<div>spa</div>"
