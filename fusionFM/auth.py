import os
from datetime import datetime, timedelta, timezone
from jose import jwt, JWTError

SECRET = os.getenv("JWT_SECRET", "dev-secret")
ALGORITHM = "HS256"


def create_token(data, expires_in=3600):
    payload = data.copy()
    payload["exp"] = datetime.now(timezone.utc) + timedelta(seconds=expires_in)
    return jwt.encode(payload, SECRET, algorithm=ALGORITHM)


def verify_token(token):
    if not token:
        return None

    try:
        return jwt.decode(token, SECRET, algorithms=[ALGORITHM])
    except JWTError:
        return None