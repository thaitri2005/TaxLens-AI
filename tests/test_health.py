from fastapi.testclient import TestClient

from taxlens.api.main import create_app


def test_health_endpoint_returns_service_status() -> None:
    client = TestClient(create_app())

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "taxlens-api"}
    assert response.headers["X-Request-ID"]


def test_ready_waits_for_migrations_but_health_answers_at_once(monkeypatch) -> None:
    import taxlens.api.main as main
    from taxlens.api.migrations import MigrationState

    monkeypatch.setattr(main, "database_is_ready", lambda: True)
    state = {"value": MigrationState.RUNNING}
    monkeypatch.setattr(main, "migration_state", lambda: state["value"])
    client = TestClient(create_app())

    assert client.get("/health").status_code == 200
    running = client.get("/ready")
    assert running.status_code == 503
    assert running.json()["detail"]["dependency"] == "migrations"

    state["value"] = MigrationState.COMPLETED
    assert client.get("/ready").status_code == 200


def test_failed_migrations_keep_the_api_out_of_rotation(monkeypatch) -> None:
    import taxlens.api.migrations as migrations

    def fail(config: object, revision: str) -> None:
        raise RuntimeError("migration failed")

    monkeypatch.setattr(migrations.command, "upgrade", fail)

    migrations.start_migrations().join(timeout=10)

    assert migrations.migration_state() is migrations.MigrationState.FAILED
    migrations.mark_migrations_skipped()
