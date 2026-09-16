DPI = 203
MAX_WIDTH_DOTS = 830
MAX_HEIGHT_DOTS = 7917

PRESETS = {
    "2x2": {"id": "2x2", "label": '2" × 2"', "width_in": 2.0, "height_in": 2.0},
    "3x2": {"id": "3x2", "label": '3" × 2"', "width_in": 3.0, "height_in": 2.0},
    "4x3": {"id": "4x3", "label": '4" × 3"', "width_in": 4.0, "height_in": 3.0},
    "4x4": {"id": "4x4", "label": '4" × 4"', "width_in": 4.0, "height_in": 4.0},
    "4x6": {"id": "4x6", "label": '4" × 6"', "width_in": 4.0, "height_in": 6.0},
    "full3": {
        "id": "full3",
        "label": '4.09" × 3" (full width)',
        "width_in": 4.09,
        "height_in": 3.0,
    },
}

DEFAULT_PRESET = "4x6"


def size_to_dots(width_in: float, height_in: float) -> tuple[int, int]:
    width_dots = min(MAX_WIDTH_DOTS, max(1, round(width_in * DPI)))
    height_dots = min(MAX_HEIGHT_DOTS, max(1, round(height_in * DPI)))
    return width_dots, height_dots


def resolve_size(
    preset: str | None,
    width_in: float | None,
    height_in: float | None,
) -> tuple[float, float, int, int, str]:
    if preset and preset != "custom" and preset in PRESETS:
        spec = PRESETS[preset]
        width_in = spec["width_in"]
        height_in = spec["height_in"]
        preset_id = spec["id"]
    else:
        if width_in is None or height_in is None:
            spec = PRESETS[DEFAULT_PRESET]
            width_in = spec["width_in"]
            height_in = spec["height_in"]
            preset_id = spec["id"]
        else:
            width_in = max(0.25, float(width_in))
            height_in = max(0.25, float(height_in))
            preset_id = "custom"

    width_dots, height_dots = size_to_dots(width_in, height_in)
    return width_in, height_in, width_dots, height_dots, preset_id
