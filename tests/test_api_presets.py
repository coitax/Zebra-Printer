from fastapi.testclient import TestClient

from app.main import app
from app.presets import DEFAULT_PRESET


client = TestClient(app)


def test_presets_endpoint_exposes_default():
    response = client.get("/api/presets")
    assert response.status_code == 200
    data = response.json()
    assert data["default"] == DEFAULT_PRESET
    assert any(preset["id"] == "4x6" for preset in data["presets"])
