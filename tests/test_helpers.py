from pathlib import Path

import asyncio
import pytest

from fusionframe import (
    AdminPanel,
    App,
    DistributedJobQueue,
    JinjaTemplateEngine,
    DispatchedJob,
    get_csrf_token,
    GraphQL,
    InMemoryJobStore,
    JobQueue,
    JobWorker,
    SQLiteJobStore,
    TemplateEngine,
    TestClient,
    get_pagination_params,
    login_user,
    mount_spa,
    mount_static,
    paginate,
    session_middleware,
)
from fusionframe.db import Base, get_db_session
from fusionframe.orm import Model
from sqlalchemy import create_engine
from sqlalchemy.orm import Mapped, mapped_column, sessionmaker


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
    assert "etag" in static_response.headers

    cached_response = client.get(
        "/static/site.css",
        headers={"if-none-match": static_response.headers["etag"]},
    )
    assert cached_response.status_code == 304

    form_response = client.post("/contact", form={"name": "Sri"})
    assert form_response.json()["form"] == {"name": "Sri"}

    boundary = "----fusionframe"
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


def test_jinja_template_engine_renders_when_installed(tmp_path):
    pytest.importorskip("jinja2")

    templates_dir = tmp_path / "jinja"
    templates_dir.mkdir()
    (templates_dir / "dashboard.html").write_text(
        "<h1>{{ title }}</h1>{% for item in items %}<span>{{ item }}</span>{% endfor %}",
        encoding="utf-8",
    )

    templates = JinjaTemplateEngine(str(templates_dir), globals={"title": "Dashboard"})
    rendered = templates.render("dashboard.html", {"items": ["a", "b"]})
    inline = templates.render_string("Hello {{ name }}", {"name": "Sri"})

    assert rendered == "<h1>Dashboard</h1><span>a</span><span>b</span>"
    assert inline == "Hello Sri"


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
    assert spa_response.headers["cache-control"] == "no-cache"


def test_admin_panel_crud_and_jobs(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'admin.db'}", echo=False)
    session_local = sessionmaker(
        bind=engine,
        autoflush=False,
        autocommit=False,
        expire_on_commit=False,
    )

    import fusionframe.db as db_module

    monkeypatch.setattr(db_module, "engine", engine)
    monkeypatch.setattr(db_module, "SessionLocal", session_local)

    class User(Model):
        __tablename__ = "users_admin_test"
        name: Mapped[str] = mapped_column(nullable=False)
        age: Mapped[int] = mapped_column(nullable=False)

    Base.metadata.create_all(bind=engine)

    app = App()
    app.use(session_middleware(secure=False))
    admin = AdminPanel(roles=["admin"])
    admin.register(User, list_display=["id", "name"], create_fields=["name", "age"])
    admin.install(app, get_db_session)

    events = []

    @app.jobs.schedule(1, name="tick")
    async def tick():
        events.append("tick")

    @app.post("/login")
    async def login(request):
        login_user(request, {"sub": "admin", "roles": ["admin"]})
        return {"ok": True, "csrf": get_csrf_token(request)}

    sent = []
    messages = [{"type": "lifespan.startup"}, {"type": "lifespan.shutdown"}]

    async def receive():
        return messages.pop(0)

    async def send(message):
        sent.append(message)

    async def run_lifespan():
        task = asyncio.create_task(app({"type": "lifespan"}, receive, send))
        await asyncio.sleep(0.3)
        await task

    asyncio.run(run_lifespan())
    assert sent[0]["type"] == "lifespan.startup.complete"
    assert events

    client = TestClient(app)
    login_response = client.post("/login", json_body={})
    cookie = login_response.headers["set-cookie"].split(";", 1)[0]
    csrf = login_response.json()["csrf"]

    form_response = client.post(
        "/admin/users_admin_test/new",
        form={"name": "Sri", "age": "25", "_csrf_token": csrf},
        headers={"cookie": cookie},
    )
    assert form_response.status_code == 201

    list_response = client.get(
        "/admin/users_admin_test",
        headers={"cookie": cookie},
        query={"q": "Sri", "page": 1, "per_page": 1},
    )
    assert list_response.status_code == 200
    assert "Sri" in list_response.text
    assert "Page 1 of 1" in list_response.text

    edit_form = client.get("/admin/users_admin_test/1/edit", headers={"cookie": cookie})
    assert edit_form.status_code == 200
    assert "Save" in edit_form.text

    edit_response = client.post(
        "/admin/users_admin_test/1/edit",
        form={"name": "Sri Updated", "age": "26", "_csrf_token": csrf},
        headers={"cookie": cookie},
    )
    assert edit_response.status_code == 200

    detail_response = client.get("/admin/users_admin_test/1", headers={"cookie": cookie})
    assert "Sri Updated" in detail_response.text

    delete_response = client.post(
        "/admin/users_admin_test/1/delete",
        form={"_csrf_token": csrf},
        headers={"cookie": cookie},
    )
    assert delete_response.status_code == 200

    Base.metadata.remove(User.__table__)
    engine.dispose()


def test_admin_model_customization_hooks(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'admin_hooks.db'}", echo=False)
    session_local = sessionmaker(
        bind=engine,
        autoflush=False,
        autocommit=False,
        expire_on_commit=False,
    )

    import fusionframe.db as db_module

    monkeypatch.setattr(db_module, "engine", engine)
    monkeypatch.setattr(db_module, "SessionLocal", session_local)

    class Product(Model):
        __tablename__ = "products_admin_hooks"
        name: Mapped[str] = mapped_column(nullable=False)
        sku: Mapped[str] = mapped_column(nullable=False)
        price: Mapped[int] = mapped_column(nullable=False)

    Base.metadata.create_all(bind=engine)

    app = App()
    app.use(session_middleware(secure=False))
    admin = AdminPanel(roles=["admin"])
    admin.register(
        Product,
        label="Catalog",
        list_display=["id", "name", "price"],
        create_fields=["name", "sku", "price"],
        edit_fields=["name", "price"],
        search_fields=["sku"],
        detail_fields=["name", "sku", "price"],
        field_labels={"name": "Product Name", "sku": "SKU", "price": "Unit Price"},
        form_widgets={"price": "number"},
        list_transform=lambda request, db, rows: list(reversed(rows)),
        create_transform=lambda request, db, payload: {**payload, "name": payload["name"].strip().title()},
        edit_transform=lambda request, db, record: (
            setattr(record, "name", record.name.upper()) or record
        ),
    )
    admin.install(app, get_db_session)

    @app.post("/login")
    async def login(request):
        login_user(request, {"sub": "admin", "roles": ["admin"]})
        return {"ok": True, "csrf": get_csrf_token(request)}

    client = TestClient(app)
    login_response = client.post("/login", json_body={})
    cookie = login_response.headers["set-cookie"].split(";", 1)[0]
    csrf = login_response.json()["csrf"]

    create_one = client.post(
        "/admin/products_admin_hooks/new",
        form={"name": " alpha ", "sku": "SKU-001", "price": "10", "_csrf_token": csrf},
        headers={"cookie": cookie},
    )
    create_two = client.post(
        "/admin/products_admin_hooks/new",
        form={"name": "beta", "sku": "SKU-002", "price": "20", "_csrf_token": csrf},
        headers={"cookie": cookie},
    )
    assert create_one.status_code == 201
    assert create_two.status_code == 201

    listing = client.get(
        "/admin/products_admin_hooks",
        headers={"cookie": cookie},
        query={"q": "SKU-002", "page": 1, "per_page": 1},
    )
    assert listing.status_code == 200
    assert "Catalog" in listing.text
    assert "Product Name" in listing.text
    assert "Unit Price" in listing.text
    assert "Beta" in listing.text
    assert "Alpha" not in listing.text
    assert "Page 1 of 1" in listing.text

    edit_form = client.get("/admin/products_admin_hooks/1/edit", headers={"cookie": cookie})
    assert edit_form.status_code == 200
    assert 'type="number"' in edit_form.text
    assert "Product Name" in edit_form.text
    assert "SKU" not in edit_form.text

    edit_response = client.post(
        "/admin/products_admin_hooks/1/edit",
        form={"name": "gamma", "price": "30", "_csrf_token": csrf},
        headers={"cookie": cookie},
    )
    assert edit_response.status_code == 200

    detail = client.get("/admin/products_admin_hooks/1", headers={"cookie": cookie})
    assert detail.status_code == 200
    assert "GAMMA" in detail.text
    assert "SKU-001" in detail.text
    assert "Unit Price" in detail.text

    Base.metadata.remove(Product.__table__)
    engine.dispose()


def test_job_queue_retry_failure_and_visibility(tmp_path):
    events = []
    attempts = {"count": 0}

    async def flaky():
        attempts["count"] += 1
        if attempts["count"] < 2:
            raise RuntimeError("temporary failure")
        events.append("done")
        return {"ok": True}

    async def run():
        queue = JobQueue()
        await queue.start()
        job_id = await queue.enqueue(flaky, max_retries=1, retry_backoff=0)
        for _ in range(20):
            record = queue.get_job(job_id)
            if record and record.status == "succeeded":
                break
            await asyncio.sleep(0.05)
        await queue.stop()
        return queue, job_id

    queue, job_id = asyncio.run(run())
    record = queue.get_job(job_id)
    assert events == ["done"]
    assert record is not None
    assert record.status == "succeeded"
    assert record.attempts == 2
    assert record.result == {"ok": True}
    assert queue.list_jobs()[0].id == job_id

    async def always_fail():
        raise RuntimeError("permanent failure")

    async def run_failed():
        queue = JobQueue()
        await queue.start()
        job_id = await queue.enqueue(always_fail, max_retries=1, retry_backoff=0)
        for _ in range(20):
            record = queue.get_job(job_id)
            if record and record.status == "failed":
                break
            await asyncio.sleep(0.05)
        await queue.stop()
        return queue.get_job(job_id)

    failed_record = asyncio.run(run_failed())
    assert failed_record is not None
    assert failed_record.status == "failed"
    assert failed_record.attempts == 2
    assert failed_record.error == "permanent failure"


def test_sqlite_job_store_persists_job_state(tmp_path):
    store_path = tmp_path / "jobs.sqlite3"

    async def run_job():
        queue = JobQueue(store=SQLiteJobStore(str(store_path)))
        await queue.start()

        async def task():
            return {"value": 1}

        job_id = await queue.enqueue(task, name="persisted-job")
        for _ in range(20):
            record = queue.get_job(job_id)
            if record and record.status == "succeeded":
                break
            await asyncio.sleep(0.05)
        await queue.stop()
        return job_id

    job_id = asyncio.run(run_job())
    persisted = SQLiteJobStore(str(store_path)).get(job_id)
    assert persisted is not None
    assert persisted.name == "persisted-job"
    assert persisted.status == "succeeded"
    assert persisted.result == {"value": 1}


def test_job_queue_timeout_and_cancellation():
    async def run_timeout():
        queue = JobQueue()
        await queue.start()

        async def slow():
            await asyncio.sleep(0.2)
            return {"ok": True}

        job_id = await queue.enqueue(slow, timeout=0.01)
        for _ in range(30):
            record = queue.get_job(job_id)
            if record and record.status == "failed":
                break
            await asyncio.sleep(0.02)
        await queue.stop()
        return queue.get_job(job_id)

    timeout_record = asyncio.run(run_timeout())
    assert timeout_record is not None
    assert timeout_record.status == "failed"
    assert "timeout" in timeout_record.error.lower()

    async def run_cancel():
        queue = JobQueue()
        started = asyncio.Event()
        release = asyncio.Event()
        await queue.start()

        async def waiting():
            started.set()
            await release.wait()

        job_id = await queue.enqueue(waiting, timeout=1)
        await started.wait()
        cancelled = await queue.cancel_job(job_id)
        await asyncio.sleep(0.05)
        await queue.stop()
        return cancelled, queue.get_job(job_id)

    cancelled, cancelled_record = asyncio.run(run_cancel())
    assert cancelled is True
    assert cancelled_record is not None
    assert cancelled_record.status == "cancelled"


def test_job_queue_honors_worker_concurrency():
    async def run():
        queue = JobQueue(store=InMemoryJobStore(), max_workers=2)
        current = 0
        peak = 0
        lock = asyncio.Lock()
        await queue.start()

        async def task():
            nonlocal current, peak
            async with lock:
                current += 1
                peak = max(peak, current)
            await asyncio.sleep(0.05)
            async with lock:
                current -= 1
            return {"ok": True}

        job_ids = [await queue.enqueue(task, name=f"job-{index}") for index in range(3)]
        for _ in range(40):
            statuses = [queue.get_job(job_id).status for job_id in job_ids]
            if all(status == "succeeded" for status in statuses):
                break
            await asyncio.sleep(0.02)
        await queue.stop()
        return peak

    peak = asyncio.run(run())
    assert peak >= 2


def test_sqlite_job_store_persists_schedule_metadata(tmp_path):
    store_path = tmp_path / "scheduled.sqlite3"
    store = SQLiteJobStore(str(store_path))
    queue = JobQueue(store=store)

    @queue.schedule(60, name="nightly-sync", max_retries=2, timeout=15)
    async def nightly_sync():
        return {"ok": True}

    schedules = store.list_schedules()
    assert len(schedules) == 1
    assert schedules[0].name == "nightly-sync"
    assert schedules[0].interval == 60
    assert schedules[0].max_retries == 2
    assert schedules[0].timeout == 15

    restored = JobQueue(store=SQLiteJobStore(str(store_path)))

    @restored.schedule(60, name="nightly-sync", max_retries=2, timeout=15)
    async def restored_sync():
        return {"ok": True}

    assert restored.list_schedules()[0].last_run == schedules[0].last_run


def test_distributed_job_queue_and_worker_with_sqlite_broker(tmp_path):
    broker = SQLiteJobStore(str(tmp_path / "distributed.sqlite3"))
    queue = DistributedJobQueue(broker)

    seen = []

    @queue.task("email.send")
    async def send_email(recipient, subject):
        seen.append((recipient, subject))
        return {"sent": True, "recipient": recipient}

    @queue.task("email.fail")
    async def fail_email(recipient):
        raise RuntimeError(f"cannot send to {recipient}")

    sent_job_id = queue.enqueue(
        "email.send",
        {"recipient": "sri@example.com", "subject": "Welcome"},
        max_retries=1,
        timeout=2,
    )
    failed_job_id = queue.enqueue(
        "email.fail",
        {"recipient": "bad@example.com"},
        max_retries=0,
        timeout=2,
    )

    worker = JobWorker(queue)
    processed = asyncio.run(worker.run_until_empty())
    sent_job = broker.get_dispatched(sent_job_id)
    failed_job = broker.get_dispatched(failed_job_id)

    assert processed
    assert seen == [("sri@example.com", "Welcome")]
    assert isinstance(sent_job, DispatchedJob)
    assert sent_job.status == "succeeded"
    assert sent_job.result == {"sent": True, "recipient": "sri@example.com"}
    assert failed_job.status == "failed"
    assert "cannot send" in failed_job.error
    assert broker.list_dispatched()[0].task_name == "email.send"
