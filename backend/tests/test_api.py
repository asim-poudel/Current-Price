import pytest
from fastapi.testclient import TestClient

import app as api


@pytest.fixture
def client():
    return TestClient(api.app, raise_server_exceptions=False)


@pytest.mark.parametrize(
    ("method", "path", "kwargs"),
    [
        ("get", "/api/forecast/current", {}),
        ("get", "/api/evaluation/latest", {}),
        ("get", "/api/evaluation/latest/series", {}),
        ("post", "/api/rag/ask", {"json": {"question": "What was yesterday's MAE?"}}),
        ("post", "/api/jobs/daily-forecast", {"headers": {"Authorization": "Bearer test-secret"}}),
    ],
)
def test_missing_database_returns_sanitized_503(client, monkeypatch, method, path, kwargs):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("RATE_LIMIT_SALT", "test-salt")
    monkeypatch.setenv("CRON_SECRET", "test-secret")
    response = getattr(client, method)(path, **kwargs)
    assert response.status_code == 503
    assert response.json() == {
        "schema_version": "1.0",
        "error": {
            "code": "database_unavailable",
            "message": "The database service is unavailable.",
        },
    }
    assert "DATABASE_URL" not in response.text


def test_health_remains_available_without_database(client, monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] == "degraded"
    assert response.json()["checks"] == {"model": "ok", "database": "error"}


def test_not_found_uses_public_error_contract(client, monkeypatch):
    monkeypatch.setattr(api.db, "latest_forecast", lambda: (None, []))
    response = client.get("/api/forecast/current")
    assert response.status_code == 404
    assert response.json()["schema_version"] == "1.0"
    assert response.json()["error"]["code"] == "not_found"


def test_validation_error_uses_public_error_contract(client):
    response = client.post("/api/rag/ask", json={})
    assert response.status_code == 422
    assert response.json()["error"] == {
        "code": "invalid_request",
        "message": "The request payload is invalid.",
    }


@pytest.mark.parametrize("origin", ["http://localhost:3000", "http://127.0.0.1:3000"])
def test_local_origins_pass_cors_preflight(client, origin):
    response = client.options(
        "/api/forecast/current",
        headers={"Origin": origin, "Access-Control-Request-Method": "GET"},
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == origin
