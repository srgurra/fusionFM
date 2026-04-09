from __future__ import annotations

import os
import hashlib
import hmac
import secrets
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
import inspect

from jose import JWTError, jwt


SECRET = os.getenv("JWT_SECRET", "dev-secret")
ALGORITHM = "HS256"
ISSUER = os.getenv("JWT_ISSUER", "fusionframe")
AUDIENCE = os.getenv("JWT_AUDIENCE")
PASSWORD_RESET_SECRET = os.getenv("PASSWORD_RESET_SECRET", f"{SECRET}-reset")
ACCOUNT_VERIFICATION_SECRET = os.getenv("ACCOUNT_VERIFICATION_SECRET", f"{SECRET}-verify")


@dataclass
class Identity:
    subject: str | None = None
    roles: list[str] = field(default_factory=list)
    permissions: list[str] = field(default_factory=list)
    claims: dict = field(default_factory=dict)

    def to_claims(self):
        payload = dict(self.claims)
        if self.subject is not None:
            payload["sub"] = self.subject
        if self.roles:
            payload["roles"] = list(self.roles)
        if self.permissions:
            payload["permissions"] = list(self.permissions)
        return payload


def normalize_identity(value) -> Identity | None:
    if value is None:
        return None

    if isinstance(value, Identity):
        return value

    if isinstance(value, dict):
        claims = dict(value)
        return Identity(
            subject=claims.get("sub"),
            roles=_normalize_list(claims.get("roles")),
            permissions=_normalize_list(claims.get("permissions")),
            claims=claims,
        )

    raise TypeError("Identity must be an Identity instance or a dict")


def create_token(data, expires_in=3600, subject=None):
    identity = normalize_identity(data) if not isinstance(data, Identity) else data
    payload = identity.to_claims() if identity else dict(data)
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
        payload = jwt.decode(
            token,
            SECRET,
            algorithms=[ALGORITHM],
            audience=AUDIENCE,
            issuer=ISSUER,
            options=options,
        )
        identity = normalize_identity(payload)
        return identity.claims
    except JWTError:
        return None


def has_role(user, *roles):
    identity = normalize_identity(user) if user is not None else None
    if identity is None:
        return False
    return bool(set(identity.roles).intersection(roles))


def has_permission(user, *permissions):
    identity = normalize_identity(user) if user is not None else None
    if identity is None:
        return False
    return set(permissions).issubset(set(identity.permissions))


def _normalize_list(value):
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    return list(value)


class PasswordHasher:
    algorithm = "pbkdf2_sha256"

    def hash(self, password: str, *, iterations: int = 600_000) -> str:
        salt = secrets.token_hex(16)
        digest = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            salt.encode("utf-8"),
            iterations,
        ).hex()
        return f"{self.algorithm}${iterations}${salt}${digest}"

    def verify(self, password: str, encoded: str) -> bool:
        try:
            algorithm, iterations, salt, digest = encoded.split("$", 3)
        except ValueError:
            return False
        if algorithm != self.algorithm:
            return False
        candidate = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            salt.encode("utf-8"),
            int(iterations),
        ).hex()
        return hmac.compare_digest(candidate, digest)


class AuthBackend:
    async def authenticate(self, identifier: str, secret: str):
        raise NotImplementedError

    async def get_identity(self, identifier: str):
        raise NotImplementedError

    async def set_password(self, identifier: str, password: str):
        raise NotImplementedError


class InMemoryAuthBackend(AuthBackend):
    def __init__(self, users=None, *, hasher=None):
        self.users = dict(users or {})
        self.hasher = hasher or PasswordHasher()

    def register(self, identifier: str, password: str, *, identity=None):
        user_identity = normalize_identity(identity or {"sub": identifier}) or Identity(subject=identifier)
        self.users[identifier] = {
            "password_hash": self.hasher.hash(password),
            "identity": user_identity.to_claims(),
        }

    async def authenticate(self, identifier: str, secret: str):
        user = self.users.get(identifier)
        if not user:
            return None
        if not self.hasher.verify(secret, user["password_hash"]):
            return None
        return user["identity"]

    async def get_identity(self, identifier: str):
        user = self.users.get(identifier)
        if not user:
            return None
        return dict(user["identity"])

    async def set_password(self, identifier: str, password: str):
        user = self.users.get(identifier)
        if not user:
            raise KeyError(identifier)
        user["password_hash"] = self.hasher.hash(password)
        return dict(user["identity"])


async def authenticate_with(backend: AuthBackend, identifier: str, secret: str):
    result = backend.authenticate(identifier, secret)
    if inspect.isawaitable(result):
        result = await result
    return result


class PasswordResetManager:
    def __init__(self, *, secret: str = PASSWORD_RESET_SECRET, issuer: str = ISSUER):
        self.secret = secret
        self.issuer = issuer

    def issue_token(self, identifier: str, *, expires_in: int = 900):
        payload = {
            "sub": identifier,
            "iat": datetime.now(timezone.utc),
            "exp": datetime.now(timezone.utc) + timedelta(seconds=expires_in),
            "iss": self.issuer,
            "purpose": "password_reset",
        }
        return jwt.encode(payload, self.secret, algorithm=ALGORITHM)

    def verify_token(self, token: str):
        try:
            payload = jwt.decode(
                token,
                self.secret,
                algorithms=[ALGORITHM],
                issuer=self.issuer,
            )
        except JWTError:
            return None
        if payload.get("purpose") != "password_reset":
            return None
        return payload.get("sub")

    async def reset_password(self, backend: AuthBackend, identifier: str, token: str, new_password: str):
        token_subject = self.verify_token(token)
        if token_subject != identifier:
            return False
        result = backend.set_password(identifier, new_password)
        if inspect.isawaitable(result):
            await result
        return True


@dataclass
class AccountRecord:
    identifier: str
    identity: dict
    verified: bool = False
    metadata: dict = field(default_factory=dict)


class AccountManager:
    def __init__(
        self,
        backend: AuthBackend,
        *,
        password_resets: PasswordResetManager | None = None,
        verification_secret: str = ACCOUNT_VERIFICATION_SECRET,
        issuer: str = ISSUER,
    ):
        self.backend = backend
        self.password_resets = password_resets or PasswordResetManager()
        self.verification_secret = verification_secret
        self.issuer = issuer
        self._accounts: dict[str, AccountRecord] = {}

    async def register(self, identifier: str, password: str, *, identity=None, verified: bool = False, metadata=None):
        backend = self.backend
        register = getattr(backend, "register", None)
        if not callable(register):
            raise TypeError("backend must implement register() for AccountManager.register")
        result = register(identifier, password, identity=identity)
        if inspect.isawaitable(result):
            await result
        claims = await self._get_identity(identifier)
        account = AccountRecord(
            identifier=identifier,
            identity=claims or normalize_identity(identity or {"sub": identifier}).to_claims(),
            verified=verified,
            metadata=dict(metadata or {}),
        )
        self._accounts[identifier] = account
        return account

    async def authenticate(self, identifier: str, password: str, *, require_verified: bool = False):
        claims = await authenticate_with(self.backend, identifier, password)
        if claims is None:
            return None
        account = self._accounts.get(identifier)
        if require_verified and account and not account.verified:
            return None
        return claims

    def issue_verification_token(self, identifier: str, *, expires_in: int = 86400):
        payload = {
            "sub": identifier,
            "iat": datetime.now(timezone.utc),
            "exp": datetime.now(timezone.utc) + timedelta(seconds=expires_in),
            "iss": self.issuer,
            "purpose": "account_verification",
        }
        return jwt.encode(payload, self.verification_secret, algorithm=ALGORITHM)

    def verify_account_token(self, token: str):
        try:
            payload = jwt.decode(
                token,
                self.verification_secret,
                algorithms=[ALGORITHM],
                issuer=self.issuer,
            )
        except JWTError:
            return None
        if payload.get("purpose") != "account_verification":
            return None
        return payload.get("sub")

    async def mark_verified(self, token: str):
        identifier = self.verify_account_token(token)
        if not identifier or identifier not in self._accounts:
            return False
        self._accounts[identifier].verified = True
        return True

    async def change_password(self, identifier: str, current_password: str, new_password: str):
        claims = await authenticate_with(self.backend, identifier, current_password)
        if claims is None:
            return False
        result = self.backend.set_password(identifier, new_password)
        if inspect.isawaitable(result):
            await result
        return True

    async def reset_password(self, identifier: str, token: str, new_password: str):
        return await self.password_resets.reset_password(
            self.backend,
            identifier,
            token,
            new_password,
        )

    async def get_account(self, identifier: str):
        account = self._accounts.get(identifier)
        if account is None:
            claims = await self._get_identity(identifier)
            if claims is None:
                return None
            account = AccountRecord(identifier=identifier, identity=claims)
            self._accounts[identifier] = account
        return account

    async def _get_identity(self, identifier: str):
        result = self.backend.get_identity(identifier)
        if inspect.isawaitable(result):
            result = await result
        return result
