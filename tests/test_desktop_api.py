from app.api_service import APP_BUILD
from app.desktop_api import Api
from app.presets import DEFAULT_PRESET


def test_api_class_returns_presets_without_http():
    data = Api().get_presets()
    assert data["default"] == DEFAULT_PRESET
    assert data["build"] == APP_BUILD
    assert any(preset["id"] == "4x6" for preset in data["presets"])
