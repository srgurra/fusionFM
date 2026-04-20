from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from dataclasses import dataclass

from .auth import Identity, create_token, normalize_identity, verify_token


SESSION_COOKIE = "fusionframe_session"
SESSION_SECRET = os.getenv("SESSION_SECRET", "fusionframe-session-secret")
SESSION_TTL = int(os.getenv("SESSION_TTL", 60 * 60 * 24 * 7))
CSRF_SESSION_KEY = "_csrf_token"


@dataclass
class SessionData:
    data: dict
    session_id: str | None = None
    is_new: bool = False
    modified: bool = False
    cleared: bool = False
    rotated: bool = False


class SessionStore:
    def load(self, session_id):
        raise NotImplementedError

    def save(self, session_id, data, ttl):
        raise NotImplementedError

    def delete(self, session_id):
        raise NotImplementedError

    def create_session_id(self):
        return secrets.token_urlsafe(32)


class InMemorySessionStore(SessionStore):
    def __init__(self):
        self._sessions = {}

    def load(self, session_id):
        record = self._sessions.get(session_id)
        if not record:
            return None
        expires_at, data = record
        if expires_at < time.time():
            self._sessions.pop(session_id, None)
            return None
        return dict(data)

    def save(self, session_id, data, ttl):
        self._sessions[session_id] = (time.time() + ttl, dict(data))

    def delete(self, session_id):
        self._sessions.pop(session_id, None)


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
    store: SessionStore | None = None,
):
    async def middleware(request, call_next):
        cookie_header = request.get_header("cookie", "")
        cookies = _parse_cookies(cookie_header)

        if store:
            session_id = cookies.get(cookie_name)
            payload = store.load(session_id) if session_id else None
            request.session = payload or {}
            request.session_meta = SessionData(
                data=request.session,
                session_id=session_id,
                is_new=payload is None,
            )
        else:
            request.session = _decode_session(cookies.get(cookie_name))
            request.session_meta = SessionData(data=request.session)

        request.session.setdefault(CSRF_SESSION_KEY, secrets.token_urlsafe(24))

        response = await call_next()
        should_secure = secure
        if should_secure is None:
            forwarded_proto = request.get_header("x-forwarded-proto", "")
            scheme = request.scope.get("scheme")
            should_secure = forwarded_proto == "https" or scheme == "https"

        cookie_parts = [f"Path={path}", f"SameSite={same_site}", f"Max-Age={SESSION_TTL}"]
        if http_only:
            cookie_parts.append("HttpOnly")
        if should_secure:
            cookie_parts.append("Secure")
        if domain:
            cookie_parts.append(f"Domain={domain}")

        meta = request.session_meta
        if meta.cleared:
            request.state["_session_cookie"] = (
                f"{cookie_name}=; Path={path}; Max-Age=0"
            )
            if store and meta.session_id:
                store.delete(meta.session_id)
            return response

        if store:
            session_id = (
                store.create_session_id()
                if meta.rotated or not meta.session_id
                else meta.session_id
            )
            store.save(session_id, request.session, SESSION_TTL)
            request.state["_session_cookie"] = "; ".join(
                [f"{cookie_name}={session_id}", *cookie_parts]
            )
        else:
            request.state["_session_cookie"] = "; ".join(
                [f"{cookie_name}={_encode_session(request.session)}", *cookie_parts]
            )
        return response

    return middleware


def set_session_value(request, key, value):
    request.session[key] = value
    if hasattr(request, "session_meta"):
        request.session_meta.modified = True


def get_session_value(request, key, default=None):
    return request.session.get(key, default)


def clear_session(request):
    request.session.clear()
    if hasattr(request, "session_meta"):
        request.session_meta.cleared = True


def set_session_user(request, user, *, token_key="_token"):
    identity = normalize_identity(user)
    if identity is None:
        raise TypeError("user must be a dict or Identity")
    request.session["user"] = identity.to_claims()
    request.session[token_key] = create_token(identity)
    if hasattr(request, "session_meta"):
        request.session_meta.modified = True


def get_session_user(request, default=None):
    user = request.session.get("user")
    if user is not None:
        identity = normalize_identity(user)
        return identity.to_claims() if identity else default

    token = request.session.get("_token")
    if token:
        return verify_token(token) or default

    return default


def login_user(request, user):
    set_session_user(request, user)
    rotate_session(request)


def logout_user(request):
    clear_session(request)


def rotate_session(request):
    if hasattr(request, "session_meta"):
        request.session_meta.rotated = True
        request.session_meta.modified = True
    request.session[CSRF_SESSION_KEY] = secrets.token_urlsafe(24)


def get_csrf_token(request):
    return request.session.setdefault(CSRF_SESSION_KEY, secrets.token_urlsafe(24))


def validate_csrf(request, token=None):
    expected = request.session.get(CSRF_SESSION_KEY)
    provided = (
        token
        or request.get_header("x-csrf-token")
        or request.form().get("_csrf_token")
        or request.body.get("_csrf_token")
    )
    return bool(expected and provided and secrets.compare_digest(expected, provided))


def csrf_middleware(
    *,
    exempt_methods=("GET", "HEAD", "OPTIONS"),
    exempt_paths=None,
):
    exempt_methods = {method.upper() for method in exempt_methods}
    exempt_paths = set(exempt_paths or [])

    async def middleware(request, call_next):
        if not hasattr(request, "method"):
            return await call_next()

        get_csrf_token(request)
        if request.method.upper() not in exempt_methods and request.path not in exempt_paths:
            if not validate_csrf(request):
                from .exceptions import HTTPException

                raise HTTPException(403, "CSRF validation failed")
        return await call_next()

    return middleware
