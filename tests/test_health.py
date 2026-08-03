from fastapi.testclient import TestClient

from taxlens.api.main import create_app


def test_health_endpoint_returns_service_status() -> None:
    client = TestClient(create_app())

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "taxlens-api"}
    assert response.headers["X-Request-ID"]
