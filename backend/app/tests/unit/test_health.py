from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_returns_ok() -> None:
    response = client.get("/health")
    assert response.status_code == 200


def test_health_response_body() -> None:
    response = client.get("/health")
    body = response.json()
    assert body["status"] == "ok"
    assert body["service"] == "ai-data-analyst-backend"


def test_health_content_type() -> None:
    response = client.get("/health")
    assert "application/json" in response.headers["content-type"]
