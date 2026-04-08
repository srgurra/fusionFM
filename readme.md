# 🚀 fusionFM

![Python](https://img.shields.io/badge/python-3.9+-blue.svg)
![ASGI](https://img.shields.io/badge/ASGI-uvicorn-green)
![License](https://img.shields.io/badge/license-MIT-orange)
![Status](https://img.shields.io/badge/status-v0.1-blue)

**fusionFM** is a modern, lightweight Python web framework built from scratch by combining ideas from FastAPI, Flask, and Django.

It is designed for:
- 🧠 Learning how frameworks work internally
- ⚡ Building async APIs
- 🧪 Experimentation and prototyping
- 🚀 Creating production-style backend systems from scratch

---

## ✨ Features

- ⚡ ASGI-based (async + high performance)
- 🧠 Routing with path params (`/users/{id}`)
- 📦 Pydantic request validation
- 🔐 JWT authentication
- 🧩 Middleware system
- 🔁 Dependency Injection (DI)
- ⚡ Redis caching + decorator support
- 🗄️ Lightweight ORM (in-memory)
- 📄 Auto OpenAPI docs
- 🌐 Swagger UI (`/docs`)
- 🖥️ CLI support (`fusionfm run`)

---

## 📦 Installation

```bash
git clone https://github.com/yourusername/fusionFM.git
cd fusionFM
pip install -e .
```

## 🚀 Quick Start

### Create `example.py`

```python
from pydantic import BaseModel
from fusionFM import App

app = App()


class User(BaseModel):
    name: str
    age: int


@app.get("/")
async def home(request):
    return {"message": "Hello from fusionFM 🚀"}


@app.post("/users", model=User)
async def create_user(request):
    return {"user": request.body}
```

## 🚀 Run the server
```bash
fusionfm run example:app
```

### 🌐 Open in Browser

After starting the server, open:

- API → http://127.0.0.1:8000  
- Docs (Swagger UI) → http://127.0.0.1:8000/docs  
- OpenAPI Schema → http://127.0.0.1:8000/openapi.json  

## 🧱 Project Structure

```text
fusionFM/
├── fusionFM/
│   ├── __init__.py
│   ├── app.py            # Core ASGI app
│   ├── routing.py        # Route matching & path params
│   ├── middleware.py     # Middleware system
│   ├── auth.py           # JWT authentication
│   ├── cache.py          # Redis caching + decorator
│   ├── di.py             # Dependency injection
│   ├── orm.py            # Lightweight ORM (in-memory)
│   ├── docs.py           # OpenAPI + Swagger UI
│   ├── http.py           # Request & Response classes
│   └── cli.py            # CLI (fusionfm run)
├── example.py            # Sample application
├── pyproject.toml        # Package configuration
└── README.md             # Documentation

## 🔐 Authentication (JWT)

```python
from fusionFM.auth import create_token

@app.post("/login")
async def login(request):
    token = create_token({"user": "admin"})
    return {"token": token}
```

## 🧩 Middleware

fusionFM provides a simple and flexible middleware system to intercept requests and responses.

Middleware functions allow you to:
- Inspect or modify requests
- Add authentication logic
- Log requests
- Handle cross-cutting concerns

---

### 📌 Example: Using Built-in Middleware

```python
from fusionFM.middleware import auth_middleware

app.middleware.add(auth_middleware)
```
## 🧩 Caching
```python
from fusionFM.cache import cache

@app.get("/users")
@cache(ttl=30)
async def get_users(request):
    return {"data": "cached response"}
```

## 🚦 Rate Limiting

fusionFM includes Redis-backed rate limiting.

```python
from fusionFM import rate_limit

@app.get("/data")
@rate_limit(limit=10, per=60)
async def data(request):
    return {"message": "ok"}
```

## 🧵 Background Tasks

fusionFM supports simple background tasks that run after the response is sent.

```python
async def send_email(name):
    print(f"Sending email to {name}")

@app.post("/users")
async def create_user(request):
    request.background.add_task(send_email, "Sri")
    return {"status": "scheduled"}
```

## 🧩 Dependency Injection
```python
def get_settings():
    return {"env": "dev"}

@app.get("/config", dependencies={"settings": get_settings})
async def config(request, settings):
    return settings
```

## 🧩 ORM(Prototype)
```python
from fusionFM.orm import Model

class User(Model):
    table = "users"

user = User()
user.name = "Sri"
user.age = 25
user.save()

User.all()
```

## API Docs
fusionFM automatically provides:
- /openapi.json → OpenAPI schema
- /docs → Swagger UI

## CLI Usage
```bash
fusionfm run example:app
```

## Options
```bash
fusionfm run example:app --port 5000
fusionfm run example:app --host 0.0.0.0
fusionfm run example:app --no-reload
```

## Requirements
- python 3.9+
- Uvicorn
- Pydantic
- Redis(optional)


## Design Philosophy
fusionFM is built to:

- Teach how modern frameworks work internally
- Provide full control over request lifecycle
- Enable deep backend/system design learning

## Limitations(v0.1)

- ❌ In-memory ORM (no persistence)
- ❌ No migrations
- ❌ No background tasks
- ❌ No WebSocket support
- ❌ Minimal error handling

## Roadmap
- ✅ Routing + Middleware
- ✅ JWT Authentication
- ✅ Dependency Injection
- 🔜 SQLite / PostgreSQL support
- 🔜 Background tasks
- 🔜 WebSockets
- 🔜 Rate limiting
- 🔜 Plugin system

## Contributing
Contributions are welcome

Feel free to:

- open issues
- submit pull requests
- Suggest features

## License
MIT License

## Inspiration
Inspired by:
- FastAPI
- Flask
- Django

🔥 If you like this project, consider giving it a ⭐ on GitHub!

### Environment variables for different databases

```bash
#SQLite
export DATABASE_URL="sqlite:///fusionfm.db"
#PostGreSQL
export DATABASE_URL="postgresql+psycopg://user:password@localhost:5432/fusionfm"
#MySQL
export DATABASE_URL="mysql+pymysql://user:password@localhost:3306/fusionfm"
```