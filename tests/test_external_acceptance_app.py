import asyncio
import json

from fusionframe import TestClient
from examples.external_acceptance.backend import create_app


class FakeExternalAPIs:
    def github_repo(self, owner, repo):
        return {
            "full_name": f"{owner}/{repo}",
            "stargazers_count": 48200,
            "language": "Python",
            "license": {"spdx_id": "BSD-3-Clause"},
        }

    def pypi_package(self, package):
        return {
            "info": {
                "name": package,
                "version": "1.2.3",
                "summary": "A tested package from a public package index",
            }
        }

    def hacker_news(self, topic):
        return {
            "hits": [
                {
                    "title": f"{topic} launch",
                    "url": "https://example.com/launch",
                    "points": 42,
                },
                {
                    "story_title": f"{topic} discussion",
                    "story_url": "https://example.com/discussion",
                    "points": 21,
                },
                {
                    "title": f"{topic} benchmark",
                    "url": "https://example.com/benchmark",
                    "points": 10,
                },
            ]
        }


def _login(client):
    response = client.post(
        "/api/login",
        json_body={"email": "demo@example.com", "password": "demo-password"},
    )
    assert response.status_code == 200
    return {
        "cookie": response.headers["set-cookie"].split(";", 1)[0],
        "csrf": response.json()["csrf"],
    }


def test_acceptance_app_public_docs_static_and_spa_paths():
    app = create_app(external_apis=FakeExternalAPIs())
    client = TestClient(app)

    home = client.get("/")
    health = client.get("/api/health")
    docs = client.get("/docs")
    openapi = client.get("/openapi.json")
    static_asset = client.get("/assets/dashboard.css")
    spa = client.get("/client")
    spa_asset = client.get("/client/assets/app.js")

    assert home.status_code == 200
    assert "fusionframe External Acceptance" in home.text
    assert health.json()["status"] == "ok"
    assert docs.status_code == 200
    assert openapi.json()["info"]["title"] == "fusionframe External Acceptance App"
    assert static_asset.status_code == 200
    assert "background" in static_asset.text
    assert spa.status_code == 200
    assert "React acceptance client" in spa.text
    assert spa_asset.status_code == 200


def test_acceptance_app_auth_csrf_external_api_and_versioned_feed():
    app = create_app(external_apis=FakeExternalAPIs())
    client = TestClient(app)

    denied = client.get("/api/me")
    assert denied.status_code == 401

    auth = _login(client)
    me = client.get("/api/me", headers={"cookie": auth["cookie"]})
    assert me.status_code == 200
    assert me.json()["user"]["sub"] == "demo@example.com"

    rejected = client.post(
        "/api/insights",
        json_body={
            "owner": "encode",
            "repo": "starlette",
            "package": "fastapi",
            "topic": "python",
        },
        headers={"cookie": auth["cookie"]},
    )
    assert rejected.status_code == 403

    accepted = client.post(
        "/api/insights",
        json_body={
            "owner": "encode",
            "repo": "starlette",
            "package": "fastapi",
            "topic": "python",
        },
        headers={"cookie": auth["cookie"], "x-csrf-token": auth["csrf"]},
    )
    body = accepted.json()
    assert accepted.status_code == 200
    assert body["repo"]["name"] == "encode/starlette"
    assert body["package"]["version"] == "1.2.3"
    assert body["score"] > 0

    feed = client.get(
        "/api/v1/feed",
        headers={"cookie": auth["cookie"]},
        query={"page": 1, "per_page": 2, "topic": "python"},
    )
    assert feed.status_code == 200
    assert len(feed.json()["items"]) == 2


def test_acceptance_app_registration_verification_forms_upload_graphql_and_background():
    app = create_app(external_apis=FakeExternalAPIs())
    client = TestClient(app)

    register = client.post(
        "/api/register",
        json_body={"email": "new@example.com", "password": "secret"},
    )
    assert register.status_code == 201

    pre_verify_login = client.post(
        "/api/login",
        json_body={"email": "new@example.com", "password": "secret"},
    )
    assert pre_verify_login.status_code == 401

    verify = client.post(
        "/api/verify",
        json_body={"token": register.json()["verification_token"]},
    )
    assert verify.status_code == 200

    auth = _login(client)
    feedback = client.post(
        "/api/feedback",
        form={"message": "works"},
        headers={"cookie": auth["cookie"], "x-csrf-token": auth["csrf"]},
    )
    assert feedback.status_code == 200
    assert feedback.json()["message"] == "works"

    background = client.post(
        "/api/background",
        json_body={},
        headers={"cookie": auth["cookie"], "x-csrf-token": auth["csrf"]},
    )
    assert background.status_code == 200
    assert "background-complete" in app.state.refreshes

    graphql = client.post(
        "/api/graphql",
        json_body={"query": "{ stats }"},
        headers={"cookie": auth["cookie"], "x-csrf-token": auth["csrf"]},
    )
    assert graphql.status_code == 200
    assert graphql.json()["data"]["stats"]["framework"] == "fusionframe"

    upload = _multipart_request(
        app,
        "/api/upload",
        auth["cookie"],
        auth["csrf"],
        field_name="artifact",
        filename="report.txt",
        content=b"acceptance report",
    )
    assert upload["status"] == 200
    assert upload["json"]["filename"] == "report.txt"
    assert upload["json"]["size"] == len(b"acceptance report")


def test_acceptance_app_jobs_and_websocket_flow():
    app = create_app(external_apis=FakeExternalAPIs())
    client = TestClient(app)
    auth = _login(client)

    async def run_job_flow():
        await app.jobs.start()
        try:
            response = await _json_request_async(
                app,
                "POST",
                "/api/jobs/refresh",
                {
                    "owner": "encode",
                    "repo": "starlette",
                    "package": "fastapi",
                    "topic": "python",
                },
                headers={"cookie": auth["cookie"], "x-csrf-token": auth["csrf"]},
            )
            assert response["status"] == 202
            job_id = response["json"]["job_id"]

            for _ in range(30):
                record = app.jobs.get_job(job_id)
                if record and record.status == "succeeded":
                    return record
                await asyncio.sleep(0.02)
            return app.jobs.get_job(job_id)
        finally:
            await app.jobs.stop()

    record = asyncio.run(run_job_flow())
    assert record is not None
    assert record.status == "succeeded"
    assert record.result["repo"]["name"] == "encode/starlette"

    sent = []
    messages = [
        {"type": "websocket.connect"},
        {
            "type": "websocket.receive",
            "text": json.dumps(
                {
                    "owner": "encode",
                    "repo": "starlette",
                    "package": "fastapi",
                    "topic": "python",
                }
            ),
        },
    ]

    async def receive():
        return messages.pop(0)

    async def send(message):
        sent.append(message)

    asyncio.run(
        app(
            {
                "type": "websocket",
                "path": "/ws/insights",
                "query_string": b"",
                "headers": [],
            },
            receive,
            send,
        )
    )

    assert sent[0]["type"] == "websocket.accept"
    assert sent[1]["type"] == "websocket.send"
    assert json.loads(sent[1]["text"])["summary"] == "encode/starlette + fastapi"
    assert sent[2]["type"] == "websocket.close"


def _multipart_request(app, path, cookie, csrf, *, field_name, filename, content):
    boundary = "----fusionframe-acceptance"
    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="{field_name}"; filename="{filename}"\r\n'
        "Content-Type: text/plain\r\n\r\n"
    ).encode("utf-8") + content + f"\r\n--{boundary}--\r\n".encode("utf-8")

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
                "path": path,
                "query_string": b"",
                "headers": [
                    (b"content-type", f"multipart/form-data; boundary={boundary}".encode("utf-8")),
                    (b"cookie", cookie.encode("utf-8")),
                    (b"x-csrf-token", csrf.encode("utf-8")),
                ],
            },
            receive,
            send,
        )
    )

    start = next(item for item in sent if item["type"] == "http.response.start")
    end = next(item for item in sent if item["type"] == "http.response.body")
    return {
        "status": start["status"],
        "json": json.loads(end["body"].decode("utf-8")),
    }


async def _json_request_async(app, method, path, payload, *, headers=None):
    sent = []
    messages = [
        {
            "type": "http.request",
            "body": json.dumps(payload).encode("utf-8"),
            "more_body": False,
        }
    ]
    raw_headers = [(b"content-type", b"application/json")]
    for key, value in (headers or {}).items():
        raw_headers.append((key.lower().encode("utf-8"), str(value).encode("utf-8")))

    async def receive():
        return messages.pop(0)

    async def send(message):
        sent.append(message)

    await app(
        {
            "type": "http",
            "method": method,
            "path": path,
            "query_string": b"",
            "headers": raw_headers,
        },
        receive,
        send,
    )

    start = next(item for item in sent if item["type"] == "http.response.start")
    end = next(item for item in sent if item["type"] == "http.response.body")
    return {
        "status": start["status"],
        "json": json.loads(end["body"].decode("utf-8")),
    }
