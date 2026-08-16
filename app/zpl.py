from __future__ import annotations

from PIL import Image

from app.presets import MAX_HEIGHT_DOTS, MAX_WIDTH_DOTS


def image_to_zpl(
    image: Image.Image,
    *,
    darkness: int = 18,
    speed: int = 2,
    copies: int = 1,
    label_width: int | None = None,
    label_height: int | None = None,
    x: int = 0,
    y: int = 0,
) -> str:
    """Encode a 1-bit image as one gap-sensed label."""
    bitmap = image.convert("1")
    label_width = min(MAX_WIDTH_DOTS, label_width or bitmap.width)
    label_height = min(MAX_HEIGHT_DOTS, label_height or bitmap.height)
    if bitmap.width != label_width or bitmap.height != label_height:
        canvas = Image.new("1", (label_width, label_height), 1)
        canvas.paste(bitmap.crop((0, 0, label_width, label_height)), (0, 0))
        bitmap = canvas

    payload, bytes_per_row = pack_bitmap(bitmap)
    total_bytes = len(payload)
    hex_data = payload.hex().upper()
    darkness = max(-30, min(30, int(darkness)))
    speed = max(2, min(5, int(speed)))
    copies = max(1, min(99, int(copies)))

    return (
        f"{label_setup(label_width, label_height)}"
        f"^PR{speed}\n"
        f"^MD{darkness}\n"
        f"^FO{x},{y}^GFA,{total_bytes},{total_bytes},{bytes_per_row},{hex_data}^FS\n"
        f"^PQ{copies}\n"
        "^XZ\n"
    )


def media_calibrate_zpl(width_dots: int, height_dots: int) -> str:
    """Force gap sensing for one label, save it, then run a media calibration."""
    return f"{label_setup(width_dots, height_dots)}^JUS\n^XZ\n~JC\n"


def label_setup(width_dots: int, height_dots: int) -> str:
    width_dots = min(MAX_WIDTH_DOTS, max(1, int(width_dots)))
    height_dots = min(MAX_HEIGHT_DOTS, max(1, int(height_dots)))
    return (
        "^XA\n"
        "^MTd\n"
        "^MNY\n"
        "^MMT\n"
        "^PON\n"
        "^LH0,0\n"
        "^LT0\n"
        "^LS0\n"
        f"^PW{width_dots}\n"
        f"^LL{height_dots}\n"
        f"^ML{max_label_length_dots(height_dots)}\n"
    )


def max_label_length_dots(height_dots: int) -> int:
    """Search far enough to find the gap, but never as far as two labels."""
    return min(MAX_HEIGHT_DOTS, max(height_dots + 60, int(height_dots * 1.2)))


def pack_bitmap(image: Image.Image) -> tuple[bytes, int]:
    """Pack a mode-1 image MSB-first. Set bits are black (print)."""
    bitmap = image.convert("1")
    width, height = bitmap.size
    pixels = bitmap.load()
    bytes_per_row = (width + 7) // 8
    data = bytearray(bytes_per_row * height)

    for y in range(height):
        row_offset = y * bytes_per_row
        for x in range(width):
            # Pillow mode 1: 0 is black, 255 is white.
            if pixels[x, y] == 0:
                data[row_offset + (x >> 3)] |= 0x80 >> (x & 7)

    return bytes(data), bytes_per_row
