# Getting Started

## Install

```bash
pip install fusionframe
```

For local development:

```bash
pip install -e .[dev]
```

## Create an app

```python
from pydantic import BaseModel
from fusionframe import App

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

## Run it

```bash
fusionframe run example:app
```

## Next

- Read [public-api.md](/Users/srilakshmi/Documents/blogs/fusionFM/docs/public-api.md) for the stable surface.
- Read [testing.md](/Users/srilakshmi/Documents/blogs/fusionFM/docs/testing.md) for test patterns.
- Read [releasing.md](/Users/srilakshmi/Documents/blogs/fusionFM/docs/releasing.md) for build and publish steps.
