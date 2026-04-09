import os
from datetime import datetime, timedelta, timezone
from jose import jwt, JWTError

SECRET = os.getenv("JWT_SECRET", "dev-secret")
ALGORITHM = "HS256"
ISSUER = os.getenv("JWT_ISSUER", "fusionFM")
AUDIENCE = os.getenv("JWT_AUDIENCE")


def create_token(data, expires_in=3600, subject=None):
    payload = data.copy()
    payload.setdefault("iat", datetime.now(timezone.utc))
    payload["exp"] = datetime.now(timezone.utc) + timedelta(seconds=expires_in)
    payload.setdefault("iss", ISSUER)
    if AUDIENCE:
        payload.setdefault("aud", AUDIENCE)
    if subject is not None:
        payload["sub"] = subject
    return jwt.encode(payload, SECRET, algorithm=ALGORITHM)


def verify_token(token):
    if not token:
        return None

    try:
        options = {"verify_aud": bool(AUDIENCE)}
        return jwt.decode(
            token,
            SECRET,
            algorithms=[ALGORITHM],
            audience=AUDIENCE,
            issuer=ISSUER,
            options=options,
        )
    except JWTError:
        return None
