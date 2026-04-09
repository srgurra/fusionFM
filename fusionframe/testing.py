import asyncio
import json
from urllib.parse import urlencode


class TestResponse:
    def __init__(self, status_code, headers, body):
        self.status_code = status_code
        self.headers = headers
        self.body = body

    @property
    def text(self):
        return self.body.decode("utf-8")

    def json(self):
        return json.loads(self.text)


class TestClient:
    __test__ = False

    def __init__(self, app):
        self.app = app

    def get(self, path, headers=None, query=None):
        return self.request("GET", path, headers=headers, query=query)

    def post(self, path, json_body=None, form=None, headers=None, query=None):
        return self.request("POST", path, json_body=json_body, form=form, headers=headers, query=query)

    def request(self, method, path, json_body=None, form=None, headers=None, query=None):
        return asyncio.run(
            self._request(
                method=method,
                path=path,
                json_body=json_body,
                form=form,
                headers=headers or {},
                query=query or {},
            )
        )

    async def _request(self, method, path, json_body=None, form=None, headers=None, query=None):
        sent = []
        body = b""
        raw_headers = []
        headers = headers or {}

        if json_body is not None:
            body = json.dumps(json_body).encode("utf-8")
            headers.setdefault("content-type", "application/json")
        elif form is not None:
            body = urlencode(form, doseq=True).encode("utf-8")
            headers.setdefault("content-type", "application/x-www-form-urlencoded")

        for key, value in headers.items():
            raw_headers.append((key.lower().encode("utf-8"), str(value).encode("utf-8")))

        query_string = urlencode(query or {}, doseq=True).encode("utf-8")
        messages = [{"type": "http.request", "body": body, "more_body": False}]

        async def receive():
            return messages.pop(0)

        async def send(message):
            sent.append(message)

        await self.app(
            {
                "type": "http",
                "method": method,
                "path": path,
                "query_string": query_string,
                "headers": raw_headers,
            },
            receive,
            send,
        )

        start = next(item for item in sent if item["type"] == "http.response.start")
        end = next(item for item in sent if item["type"] == "http.response.body")
        headers_map = {
            key.decode("latin-1"): value.decode("latin-1")
            for key, value in start["headers"]
        }
        return TestResponse(start["status"], headers_map, end["body"])
