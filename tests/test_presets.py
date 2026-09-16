from app.presets import DEFAULT_PRESET, PRESETS, resolve_size, size_to_dots


def test_default_preset_is_4x6():
    assert DEFAULT_PRESET == "4x6"
    spec = PRESETS[DEFAULT_PRESET]
    assert spec["width_in"] == 4.0
    assert spec["height_in"] == 6.0


def test_size_to_dots_4x6():
    width_dots, height_dots = size_to_dots(4.0, 6.0)
    assert width_dots == 812
    assert height_dots == 1218


def test_resolve_size_uses_default_when_missing():
    width_in, height_in, width_dots, height_dots, preset_id = resolve_size(None, None, None)
    assert preset_id == "4x6"
    assert width_in == 4.0
    assert height_in == 6.0
    assert width_dots == 812
    assert height_dots == 1218


def test_resolve_size_honors_explicit_preset():
    width_in, height_in, width_dots, height_dots, preset_id = resolve_size("4x4", None, None)
    assert preset_id == "4x4"
    assert height_dots == 812
