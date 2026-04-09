import json
import dataclasses
from email.parser import BytesParser
from email.policy import default
from urllib.parse import parse_qs

MAX_BODY_SIZE = 1024 * 1024 * 10


class BackgroundTasks:
    def __init__(self):
        self.tasks = []

    def add_task(self, func, *args, **kwargs):
        self.tasks.append((func, args, kwargs))


class Request:
    def __init__(self, scope, body=None, params=None, raw_body=b"", form=None, files=None):
        self.scope = scope
        self.method = scope["method"]
        self.path = scope["path"]
        self.params = params or {}
        self.body = body or {}
        self.raw_body = raw_body or b""
        self.query = parse_qs(scope.get("query_string", b"").decode("utf-8"))
        self.headers = {
            k.decode("latin-1"): v.decode("latin-1")
            for k, v in scope.get("headers", [])
        }
        self.form_data = form or {}
        self.files = files or {}
        self.state = {}
        self.user = None
        self.session = {}
        self.background = BackgroundTasks()

    def get_header(self, name, default=None):
        return self.headers.get(name.lower(), default)

    def text(self, encoding="utf-8"):
        return self.raw_body.decode(encoding)

    def json(self):
        return json.loads(self.raw_body.decode("utf-8")) if self.raw_body else None

    def form(self):
        return self.form_data


class UploadedFile:
    def __init__(self, filename, content, content_type="application/octet-stream"):
        self.filename = filename
        self.content = content
        self.content_type = content_type
        self.size = len(content)

    def read(self):
        return self.content

    def save(self, path):
        with open(path, "wb") as output:
            output.write(self.content)


def parse_http_body(headers, body_bytes):
    content_type = headers.get("content-type", "")
    if not body_bytes:
        return {}, {}, {}

    if "application/json" in content_type:
        return json.loads(body_bytes), {}, {}

    if "application/x-www-form-urlencoded" in content_type:
        form = _simplify_values(parse_qs(body_bytes.decode("utf-8")))
        return form, form, {}

    if "multipart/form-data" in content_type:
        form, files = _parse_multipart(content_type, body_bytes)
        data = {**form, **files}
        return data, form, files

    if "text/" in content_type:
        text = body_bytes.decode("utf-8")
        return {"text": text}, {}, {}

    return {"raw": body_bytes}, {}, {}


def validate_body_size(body_bytes, max_body_size=MAX_BODY_SIZE):
    if len(body_bytes) > max_body_size:
        raise ValueError(f"Request body too large (max {max_body_size} bytes)")


def _parse_multipart(content_type, body_bytes):
    payload = f"Content-Type: {content_type}\r\nMIME-Version: 1.0\r\n\r\n".encode("utf-8") + body_bytes
    message = BytesParser(policy=default).parsebytes(payload)

    form = {}
    files = {}
    for part in message.iter_parts():
        name = part.get_param("name", header="content-disposition")
        filename = part.get_filename()
        content = part.get_payload(decode=True) or b""

        if not name:
            continue

        if filename:
            files[name] = UploadedFile(
                filename=filename,
                content=content,
                content_type=part.get_content_type(),
            )
            continue

        charset = part.get_content_charset() or "utf-8"
        form[name] = content.decode(charset)

    return form, files


def _simplify_values(values):
    simplified = {}
    for key, value in values.items():
        simplified[key] = value[0] if len(value) == 1 else value
    return simplified


class WebSocket:
    def __init__(self, scope, receive, send, params=None):
        self.scope = scope
        self.receive = receive
        self.send = send
        self.path = scope["path"]
        self.params = params or {}
        self.query = parse_qs(scope.get("query_string", b"").decode("utf-8"))
        self.headers = {
            k.decode("latin-1"): v.decode("latin-1")
            for k, v in scope.get("headers", [])
        }
        self.state = {}
        self.user = None
        self.accepted = False
        self.closed = False

    def get_header(self, name, default=None):
        return self.headers.get(name.lower(), default)

    async def accept(self, subprotocol=None, headers=None):
        if self.accepted or self.closed:
            return

        raw_headers = []
        for key, value in (headers or {}).items():
            raw_headers.append(
                (key.lower().encode("utf-8"), str(value).encode("utf-8"))
            )

        message = {"type": "websocket.accept", "headers": raw_headers}
        if subprotocol:
            message["subprotocol"] = subprotocol

        await self.send(message)
        self.accepted = True

    async def close(self, code=1000, reason=""):
        if self.closed:
            return

        await self.send(
            {"type": "websocket.close", "code": code, "reason": reason}
        )
        self.closed = True

    async def receive_message(self):
        message = await self.receive()
        if message["type"] == "websocket.disconnect":
            self.closed = True
        return message

    async def receive_text(self):
        message = await self.receive_message()
        if message["type"] != "websocket.receive":
            return None
        return message.get("text")

    async def receive_bytes(self):
        message = await self.receive_message()
        if message["type"] != "websocket.receive":
            return None
        return message.get("bytes")

    async def receive_json(self):
        text = await self.receive_text()
        if text is None:
            return None
        return json.loads(text)

    async def send_text(self, data):
        await self.send({"type": "websocket.send", "text": data})

    async def send_bytes(self, data):
        await self.send({"type": "websocket.send", "bytes": data})

    async def send_json(self, data):
        await self.send_text(json.dumps(data))


class Response:
    def __init__(self, content="", status_code=200, headers=None, content_type="text/plain; charset=utf-8"):
        self.content = content
        self.status_code = status_code
        self.headers = headers or {}
        self.content_type = content_type

    def render(self):
        if isinstance(self.content, bytes):
            return self.content
        if isinstance(self.content, str):
            return self.content.encode("utf-8")
        return str(self.content).encode("utf-8")


class JSONResponse(Response):
    def __init__(self, content, status_code=200, headers=None):
        super().__init__(
            content=content,
            status_code=status_code,
            headers=headers,
            content_type="application/json",
        )

    def render(self):
        return json.dumps(self.content, default=_json_default).encode("utf-8")


def _json_default(value):
    if dataclasses.is_dataclass(value):
        return dataclasses.asdict(value)

    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        return model_dump()

    dict_method = getattr(value, "to_dict", None)
    if callable(dict_method):
        return dict_method()

    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")
