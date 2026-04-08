from pydantic import BaseModel
from sqlalchemy.orm import Mapped, mapped_column

from fusionFM import App
from fusionFM.orm import Model
from fusionFM.db import init_db, get_db_session

app = App(title="fusionFM Demo", version="0.3.0")
init_db()


class UserInput(BaseModel):
    name: str
    age: int


class User(Model):
    __tablename__ = "users"

    name: Mapped[str] = mapped_column(nullable=False)
    age: Mapped[int] = mapped_column(nullable=False)


@app.get("/")
async def home(request):
    return {"message": "Hello from fusionFM + SQLAlchemy"}
    

@app.post("/users", model=UserInput, dependencies={"db": get_db_session})
async def create_user(request, db):
    body = request.body
    user = User(name=body["name"], age=body["age"]).save(db)
    return user.to_dict(), 201


@app.get("/users", dependencies={"db": get_db_session})
async def list_users(request, db):
    users = [u.to_dict() for u in User.all(db)]
    return {"users": users}


@app.get("/users/{id}", dependencies={"db": get_db_session})
async def get_user(request, db):
    user = User.get(db, int(request.params["id"]))
    if not user:
        return {"error": "User not found"}, 404
    return user.to_dict()