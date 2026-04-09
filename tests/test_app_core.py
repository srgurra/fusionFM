import asyncio
from pydantic import BaseModel

from fusionframe import App, HTTPException, TestClient


class UserInput(BaseModel):
    name: str


def test_json_validation_and_path_params():
    app = App()

    @app.post("/users/{user_id}", model=UserInput)
    async def create_user(request):
        return {
            "user_id": request.params["user_id"],
            "name": request.body["name"],
        }, 201

    client = TestClient(app)
    response = client.post("/users/42", json_body={"name": "Sri"})

    assert response.status_code == 201
    assert response.json() == {"user_id": "42", "name": "Sri"}


def test_validation_errors_return_422():
    app = App()

    @app.post("/users", model=UserInput)
    async def create_user(request):
        return {"ok": True}

    client = TestClient(app)
    response = client.post("/users", json_body={"age": 1})

    assert response.status_code == 422
    assert response.json()["error"] == "Validation Error"


def test_http_exception_and_custom_handler():
    app = App()

    @app.exception_handler(ValueError)
    def handle_value_error(exc):
        return {"error": "bad input", "detail": str(exc)}, 400

    @app.get("/missing")
    async def missing(request):
        raise HTTPException(404, "not here")

    @app.get("/value")
    async def value(request):
        raise ValueError("bad value")

    client = TestClient(app)

    missing_response = client.get("/missing")
    assert missing_response.status_code == 404
    assert missing_response.json()["error"] == "not here"

    value_response = client.get("/value")
    assert value_response.status_code == 400
    assert value_response.json()["detail"] == "bad value"


def test_startup_and_shutdown_hooks_record_timing():
    app = App()

    @app.on_startup
    async def startup():
        app.state["started"] = True

    @app.on_shutdown
    async def shutdown():
        app.state["stopped"] = True

    sent = []
    messages = [{"type": "lifespan.startup"}, {"type": "lifespan.shutdown"}]

    async def receive():
        return messages.pop(0)

    async def send(message):
        sent.append(message)

    asyncio.run(app({"type": "lifespan"}, receive, send))

    assert sent[0]["type"] == "lifespan.startup.complete"
    assert sent[1]["type"] == "lifespan.shutdown.complete"
    assert app.state["started"] is True
    assert app.state["stopped"] is True
    assert isinstance(app.state["startup_time_ms"], float)
