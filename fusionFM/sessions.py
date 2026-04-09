from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time

from .auth import create_token, verify_token


SESSION_COOKIE = "fusionfm_session"
SESSION_SECRET = os.getenv("SESSION_SECRET", "fusionfm-session-secret")
SESSION_TTL = int(os.getenv("SESSION_TTL", 60 * 60 * 24 * 7))


def _sign(value):
    return hmac.new(
        SESSION_SECRET.encode("utf-8"),
        value.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def _encode_session(data):
    session_data = dict(data)
    session_data.setdefault("_issued_at", int(time.time()))
    session_data["_expires_at"] = int(time.time()) + SESSION_TTL
    payload = base64.urlsafe_b64encode(
        json.dumps(session_data, separators=(",", ":")).encode("utf-8")
    ).decode("utf-8")
    return f"{payload}.{_sign(payload)}"


def _decode_session(value):
    if not value or "." not in value:
        return {}

    payload, signature = value.rsplit(".", 1)
    if not hmac.compare_digest(signature, _sign(payload)):
        return {}

    try:
        decoded = base64.urlsafe_b64decode(payload.encode("utf-8"))
        session = json.loads(decoded.decode("utf-8"))
        if session.get("_expires_at", 0) < int(time.time()):
            return {}
        return session
    except Exception:
        return {}


def _parse_cookies(header):
    cookies = {}
    for chunk in (header or "").split(";"):
        if "=" not in chunk:
            continue
        key, value = chunk.strip().split("=", 1)
        cookies[key] = value
    return cookies


def session_middleware(
    cookie_name=SESSION_COOKIE,
    *,
    secure=None,
    http_only=True,
    same_site="Lax",
    path="/",
    domain=None,
):
    async def middleware(request, call_next):
        cookie_header = request.get_header("cookie", "")
        cookies = _parse_cookies(cookie_header)
        request.session = _decode_session(cookies.get(cookie_name))

        response = await call_next()
        should_secure = secure
        if should_secure is None:
            forwarded_proto = request.get_header("x-forwarded-proto", "")
            scheme = request.scope.get("scheme")
            should_secure = forwarded_proto == "https" or scheme == "https"

        cookie_parts = [
            f"{cookie_name}={_encode_session(request.session)}",
            f"Path={path}",
            f"SameSite={same_site}",
            f"Max-Age={SESSION_TTL}",
        ]
        if http_only:
            cookie_parts.append("HttpOnly")
        if should_secure:
            cookie_parts.append("Secure")
        if domain:
            cookie_parts.append(f"Domain={domain}")

        request.state["_session_cookie"] = "; ".join(cookie_parts)
        return response

    return middleware


def set_session_value(request, key, value):
    request.session[key] = value


def get_session_value(request, key, default=None):
    return request.session.get(key, default)


def clear_session(request):
    request.session.clear()


def set_session_user(request, user, *, token_key="_token"):
    request.session["user"] = user
    request.session[token_key] = create_token(user)


def get_session_user(request, default=None):
    user = request.session.get("user")
    if user is not None:
        return user

    token = request.session.get("_token")
    if token:
        return verify_token(token) or default

    return default
