# Testing

`fusionframe` ships with a lightweight `TestClient` for synchronous tests over the ASGI app.

## Basic example

```python
from fusionframe import App, TestClient

app = App()


@app.get("/")
async def home(request):
    return {"ok": True}


def test_home():
    client = TestClient(app)
    response = client.get("/")
    assert response.status_code == 200
    assert response.json() == {"ok": True}
```

## What to test

- route matching and path params
- request parsing for JSON, form, and multipart bodies
- validation failures
- middleware effects
- sessions and auth behavior
- lifecycle hooks
- CLI commands
- migrations

## Repo commands

```bash
pytest -q
python -m compileall fusionframe tests example.py
```
