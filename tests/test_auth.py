import hashlib
import hmac
import time
import uuid

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from taxlens.api.auth import hash_password
from taxlens.api.main import create_app
from taxlens.config import get_settings
from taxlens.db import get_db_session
from taxlens.legal_data.models import UserAccount

TOKEN = "test-internal-token"


def test_login_and_protected_routes(monkeypatch) -> None:
    engine = _engine_with_users()
    admin = _add_user(engine, "admin", "admin-password-123", "admin")
    _configure_auth(monkeypatch)
    client = _client(engine)

    login = client.post(
        "/auth/login",
        headers={"X-TaxLens-Internal-Token": TOKEN},
        json={"username": "admin", "password": "admin-password-123"},
    )
    assert login.status_code == 200
    assert login.json()["role"] == "admin"
    assert client.get("/documents").status_code == 401
    assert client.get("/documents", headers=_identity_headers(admin, "admin")).status_code == 200


def test_disabled_users_cannot_use_existing_identity(monkeypatch) -> None:
    engine = _engine_with_users()
    user = _add_user(engine, "disabled", "user-password-123", "user", active=False)
    _configure_auth(monkeypatch)
    response = _client(engine).get("/documents", headers=_identity_headers(user, "disabled"))
    assert response.status_code == 401


def test_admin_operations_require_admin_role(monkeypatch) -> None:
    engine = _engine_with_users()
    user = _add_user(engine, "user", "user-password-123", "user")
    admin = _add_user(engine, "admin", "admin-password-123", "admin")
    _configure_auth(monkeypatch)
    client = _client(engine)
    response = client.get("/admin/users", headers=_identity_headers(user, "user"))
    assert response.status_code == 403
    response = client.get("/admin/users", headers=_identity_headers(admin, "admin"))
    assert response.status_code == 200


def _configure_auth(monkeypatch) -> None:
    monkeypatch.setenv("AUTH_INTERNAL_TOKEN", TOKEN)
    get_settings.cache_clear()


def _engine_with_users():
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    UserAccount.metadata.create_all(engine)
    return engine


def _add_user(engine, username: str, password: str, role: str, active: bool = True):
    with Session(engine) as session:
        user = UserAccount(
            username=username,
            password_hash=hash_password(password),
            role=role,
            is_active=active,
        )
        session.add(user)
        session.commit()
        session.refresh(user)
        return user


def _client(engine):
    app = create_app()

    def override_session():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_db_session] = override_session
    return TestClient(app)


def _identity_headers(user: UserAccount, username: str) -> dict[str, str]:
    timestamp = str(int(time.time()))
    payload = f"{user.id}:{username}:{user.role}:{timestamp}"
    signature = hmac.new(TOKEN.encode(), payload.encode(), hashlib.sha256).hexdigest()
    return {
        "X-TaxLens-User-Id": str(uuid.UUID(str(user.id))),
        "X-TaxLens-Username": username,
        "X-TaxLens-Role": user.role,
        "X-TaxLens-Auth-Timestamp": timestamp,
        "X-TaxLens-Auth-Signature": signature,
    }


def test_repeated_failed_logins_are_throttled_per_username(monkeypatch) -> None:
    from taxlens.api.auth import login_failure_limiter

    engine = _engine_with_users()
    _add_user(engine, "victim", "correct-password-123", "user")
    _configure_auth(monkeypatch)
    monkeypatch.setenv("AUTH_LOGIN_MAX_FAILURES", "2")
    get_settings.cache_clear()
    login_failure_limiter.reset("victim")
    client = _client(engine)

    def login(password: str) -> int:
        return client.post(
            "/auth/login",
            headers={"X-TaxLens-Internal-Token": TOKEN},
            json={"username": "victim", "password": password},
        ).status_code

    assert login("wrong-1") == 401
    assert login("wrong-2") == 401
    assert login("correct-password-123") == 429
    login_failure_limiter.reset("victim")
    assert login("correct-password-123") == 200


def test_admin_cannot_disable_self_and_can_re_enable_users(monkeypatch) -> None:
    engine = _engine_with_users()
    admin = _add_user(engine, "admin", "admin-password-123", "admin")
    user = _add_user(engine, "user", "user-password-123", "user", active=False)
    _configure_auth(monkeypatch)
    client = _client(engine)
    headers = _identity_headers(admin, "admin")

    assert client.post(f"/admin/users/{admin.id}/disable", headers=headers).status_code == 400
    enabled = client.post(f"/admin/users/{user.id}/enable", headers=headers)
    assert enabled.status_code == 200
    assert enabled.json()["is_active"] is True
