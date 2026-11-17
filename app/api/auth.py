"""Login, JWT issue/verify and the current-user endpoint. Requirements 7.2, 7.3, 7.4, 17.4.

* Passwords are hashed with argon2id (argon2-cffi defaults) and verified in constant time; an unknown
  username is verified against a dummy hash so timing does not reveal whether the user exists.
* ``POST /api/auth/login`` returns a 30-minute HS256 JWT carrying ``sub`` (user id), ``role``, ``jti``.
* Every login attempt is audited (``login`` / ``login_failed``); the password is never logged.
* Bad credentials and inactive users get the same generic 401.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field
from sqlalchemy import select

from app import ratelimit
from app.db import audit
from app.db.models import User
from app.db.session import get_session
from app.settings import get_settings

ROLES = ("Investigator", "Ops_Manager", "Fraud_Team", "Administrator")
ALGORITHM = "HS256"
GENERIC_LOGIN_ERROR = "Invalid username or password."

router = APIRouter(tags=["auth"])
_hasher = PasswordHasher()  # argon2id
_bearer = HTTPBearer(auto_error=False)
_DUMMY_HASH = _hasher.hash("dummy-password-for-constant-time-verify")


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(stored_hash: str | None, password: str) -> bool:
    """Constant-work verify: a missing hash is checked against a dummy so timing stays similar."""
    try:
        _hasher.verify(stored_hash or _DUMMY_HASH, password)
        return stored_hash is not None
    except (VerificationError, InvalidHashError):
        return False


# ---------------------------------------------------------------- tokens
def _secret() -> str:
    s = get_settings().jwt_secret
    value = s.get_secret_value() if s else ""
    if not value:
        raise HTTPException(503, "Login is unavailable: JWT_SECRET is not configured on the server.")
    return value


def issue_token(user_id: str, role: str, now: datetime | None = None) -> tuple[str, int]:
    """Return (jwt, expires_in_seconds)."""
    ttl = timedelta(minutes=get_settings().jwt_ttl_minutes)
    now = now or datetime.now(timezone.utc)
    claims = {"sub": str(user_id), "role": role, "jti": uuid.uuid4().hex,
              "iat": int(now.timestamp()), "exp": int((now + ttl).timestamp())}
    return jwt.encode(claims, _secret(), algorithm=ALGORITHM), int(ttl.total_seconds())


def decode_token(token: str) -> dict:
    """Verify signature and expiry. Raises HTTP 401 for any invalid token."""
    try:
        claims = jwt.decode(token, _secret(), algorithms=[ALGORITHM],
                            options={"require": ["exp", "sub", "role", "jti"]})
    except jwt.PyJWTError:
        raise HTTPException(401, "Invalid or expired token.", headers={"WWW-Authenticate": "Bearer"})
    if claims["role"] not in ROLES:
        raise HTTPException(401, "Invalid or expired token.", headers={"WWW-Authenticate": "Bearer"})
    return claims


@dataclass(frozen=True)
class CurrentUser:
    id: str
    username: str
    role: str
    jti: str


def current_user(creds: HTTPAuthorizationCredentials | None = Depends(_bearer)) -> CurrentUser:
    """Resolve the bearer token to an active user (role is taken from the database, not the token)."""
    if creds is None or creds.scheme.lower() != "bearer":
        raise HTTPException(401, "Authentication required.", headers={"WWW-Authenticate": "Bearer"})
    claims = decode_token(creds.credentials)
    try:
        uid = uuid.UUID(claims["sub"])
    except (ValueError, TypeError):
        raise HTTPException(401, "Invalid or expired token.", headers={"WWW-Authenticate": "Bearer"})
    with get_session() as session:
        user = session.get(User, uid)
        if user is None or not user.is_active:
            raise HTTPException(401, "Invalid or expired token.", headers={"WWW-Authenticate": "Bearer"})
        return CurrentUser(id=str(user.id), username=user.username, role=user.role, jti=claims["jti"])


# ---------------------------------------------------------------- login
_login_limiter: ratelimit.SlidingWindowLimiter | None = None


def login_limiter() -> ratelimit.SlidingWindowLimiter:
    global _login_limiter
    if _login_limiter is None:
        limit, window = ratelimit.parse_rate(get_settings().login_rate)
        _login_limiter = ratelimit.SlidingWindowLimiter(limit, window)
    return _login_limiter


def reset_login_limiter() -> None:
    global _login_limiter
    _login_limiter = None


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=1, max_length=256)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    role: str


class MeResponse(BaseModel):
    id: str
    username: str
    role: str


@router.post("/api/auth/login", response_model=TokenResponse)
def login(body: LoginRequest, request: Request):
    _secret()  # 503 before touching the database when unconfigured
    username = body.username.strip()
    ip = request.client.host if request.client else "unknown"
    wait = login_limiter().acquire([f"ip:{ip}", f"user:{username.lower()}"])
    if wait is not None:
        raise HTTPException(429, "Too many login attempts. Please wait and try again.",
                            headers={"Retry-After": str(ratelimit.retry_after_seconds(wait))})

    token = None
    with get_session() as session:
        user = session.scalars(select(User).where(User.username == username)).first()
        password_ok = verify_password(user.password_hash if user else None, body.password)
        if user is not None and password_ok and user.is_active:
            token, expires_in = issue_token(str(user.id), user.role)
            audit.log_login(session, str(user.id), True)
            role = user.role
        else:
            audit.log_login(session, str(user.id) if user else None, False)
    # The failure audit event is committed when the session block exits cleanly.
    if token is None:
        raise HTTPException(401, GENERIC_LOGIN_ERROR, headers={"WWW-Authenticate": "Bearer"})
    return TokenResponse(access_token=token, expires_in=expires_in, role=role)


@router.get("/api/me", response_model=MeResponse)
def me(user: CurrentUser = Depends(current_user)):
    return MeResponse(id=user.id, username=user.username, role=user.role)
