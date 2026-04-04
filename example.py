from pydantic import BaseModel

from fusionFM import App, Model
from fusionFM.auth import create_token
from fusionFM.middleware import auth_middleware, logging_middleware
from fusionFM.cache import cache


app = App(title="fusionFM Demo", version="0.1.0")
app.middleware.add(logging_middleware)
app.middleware.add(auth_middleware)


class UserInput(BaseModel):
    name: str
    age: int


class LoginInput(BaseModel):
    username: str
    password: str


class UserRecord(Model):
    table = "users"

    def __init__(self, name, age):
        self.name = name
        self.age = age


def get_settings():
    return {"env": "dev"}


@app.get("/")
async def home(request):
    return {"message": "Welcome to fusionFM"}


@app.post("/login", model=LoginInput)
async def login(request):
    body = request.body

    if body["username"] != "admin" or body["password"] != "admin123":
        return {"error": "Invalid credentials"}, 401

    token = create_token({"user": body["username"]})
    return {"token": token}


@app.post("/users", model=UserInput, dependencies={"settings": get_settings})
async def create_user(request, settings):
    body = request.body
    user = UserRecord(body["name"], body["age"]).save()

    return {
        "saved": user.to_dict(),
        "settings": settings,
    }


@app.get("/users")
@cache(ttl=30)
async def list_users(request):
    return {"users": UserRecord.all()}


@app.get("/users/{id}")
async def get_user(request):
    user_id = int(request.params["id"])
    user = UserRecord.get(id=user_id)

    if not user:
        return {"error": "User not found"}, 404

    return {
        "user": user,
        "auth_user": request.user,
    }