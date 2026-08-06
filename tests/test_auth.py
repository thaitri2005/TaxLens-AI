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
