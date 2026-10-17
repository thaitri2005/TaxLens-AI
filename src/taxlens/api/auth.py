import hashlib
import hmac
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from functools import lru_cache
from threading import Lock
from typing import Annotated

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from fastapi import Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from taxlens.config import get_settings
from taxlens.db import get_db_session
from taxlens.legal_data.models import UserAccount

password_hasher = PasswordHasher()
dependency = Depends()


@dataclass(frozen=True)
class AuthenticatedUser:
    id: uuid.UUID
    username: str
    role: str


def hash_password(password: str) -> str:
    return password_hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return password_hasher.verify(password_hash, password)
    except (InvalidHashError, VerificationError, VerifyMismatchError):
        return False


def require_internal_token(x_taxlens_internal_token: str | None = Header(default=None)) -> None:
    expected = get_settings().auth_internal_token
    if (
        not expected
        or not x_taxlens_internal_token
        or not hmac.compare_digest(x_taxlens_internal_token, expected)
    ):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized")


def require_authenticated_user(
    session: Annotated[Session, Depends(get_db_session)],
    x_taxlens_user_id: str | None = Header(default=None),
    x_taxlens_username: str | None = Header(default=None),
    x_taxlens_role: str | None = Header(default=None),
    x_taxlens_auth_timestamp: str | None = Header(default=None),
    x_taxlens_auth_signature: str | None = Header(default=None),
) -> AuthenticatedUser:
    settings = get_settings()
    values = [
        x_taxlens_user_id,
        x_taxlens_username,
        x_taxlens_role,
        x_taxlens_auth_timestamp,
        x_taxlens_auth_signature,
    ]
    if not settings.auth_internal_token or any(value is None for value in values):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required"
        )
    assert x_taxlens_user_id and x_taxlens_username and x_taxlens_role
    assert x_taxlens_auth_timestamp and x_taxlens_auth_signature
    try:
        user_id = uuid.UUID(x_taxlens_user_id)
        timestamp = int(x_taxlens_auth_timestamp)
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid identity"
        ) from error
    if abs(int(time.time()) - timestamp) > 60:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Expired identity")
    payload = f"{user_id}:{x_taxlens_username}:{x_taxlens_role}:{timestamp}".encode()
    expected = hmac.new(settings.auth_internal_token.encode(), payload, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, x_taxlens_auth_signature):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid identity")
    if x_taxlens_role not in {"admin", "user"}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid role")
    user = session.scalar(select(UserAccount).where(UserAccount.id == user_id))
    if (
        user is None
        or not user.is_active
        or user.username != x_taxlens_username
        or user.role != x_taxlens_role
    ):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Account is inactive")
    return AuthenticatedUser(id=user.id, username=user.username, role=user.role)


def require_admin(
    user: Annotated[AuthenticatedUser, Depends(require_authenticated_user)],
) -> AuthenticatedUser:
    if user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Administrator access required"
        )
    return user


class SlidingWindowRateLimiter:
    """In-process sliding-window limiter; the API runs as a single replica."""

    def __init__(
        self,
        limit: Callable[[], int],
        window_seconds: Callable[[], float],
        detail: str,
        max_keys: int = 10_000,
    ) -> None:
        self._limit = limit
        self._window_seconds = window_seconds
        self._detail = detail
        self._max_keys = max_keys
        self._lock = Lock()
        self._events: dict[str, list[float]] = {}

    def check(self, key: str) -> None:
        """Reject the call when the key is over its limit; otherwise count it."""

        with self._lock:
            self._raise_if_limited(key)
            self._record(key)

    def ensure_allowed(self, key: str) -> None:
        with self._lock:
            self._raise_if_limited(key)

    def record(self, key: str) -> None:
        with self._lock:
            self._record(key)

    def reset(self, key: str) -> None:
        with self._lock:
            self._events.pop(key, None)

    def _raise_if_limited(self, key: str) -> None:
        if len(self._recent(key, _now())) >= self._limit():
            raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=self._detail)

    def _record(self, key: str) -> None:
        now = _now()
        self._events[key] = [*self._recent(key, now), now]
        if len(self._events) > self._max_keys:
            # Keys can come from unauthenticated input (login usernames); keep memory bounded.
            for stale_key in [item for item in self._events if not self._recent(item, now)]:
                del self._events[stale_key]
            while len(self._events) > self._max_keys:
                del self._events[next(iter(self._events))]

    def _recent(self, key: str, now: float) -> list[float]:
        window = self._window_seconds()
        return [timestamp for timestamp in self._events.get(key, []) if now - timestamp < window]


def _now() -> float:
    return datetime.now(UTC).timestamp()


ask_rate_limiter = SlidingWindowRateLimiter(
    limit=lambda: get_settings().auth_rate_limit_per_minute,
    window_seconds=lambda: 60,
    detail="Ask rate limit exceeded",
)
login_failure_limiter = SlidingWindowRateLimiter(
    limit=lambda: get_settings().auth_login_max_failures,
    window_seconds=lambda: get_settings().auth_login_failure_window_seconds,
    detail="Too many failed sign-in attempts; try again later",
)


@lru_cache(maxsize=1)
def dummy_password_hash() -> str:
    """A hash to verify against for unknown usernames, so timing does not reveal them."""

    return password_hasher.hash(uuid.uuid4().hex)
