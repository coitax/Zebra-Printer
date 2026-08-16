from __future__ import annotations

from PIL import Image, ImageDraw, ImageFont

from app.image_pipeline import _to_one_bit


def build_calibration_image(width: int, height: int) -> Image.Image:
    """Draw a 1-bit target that must stay inside one label."""
    gray = Image.new("L", (width, height), 255)
    draw = ImageDraw.Draw(gray)
    font = _font(max(14, min(28, width // 28)))
    small = _font(max(12, min(20, width // 36)))

    draw.rectangle((0, 0, width - 1, height - 1), outline=0, width=3)
    draw.rectangle((6, 6, width - 7, height - 7), outline=0, width=1)
    for cx, cy in ((0, 0), (width - 1, 0), (0, height - 1), (width - 1, height - 1)):
        draw.line((cx, cy, cx + (18 if cx == 0 else -18), cy), fill=0, width=4)
        draw.line((cx, cy, cx, cy + (18 if cy == 0 else -18)), fill=0, width=4)

    inches_w = width / 203
    inches_h = height / 203
    draw.text((16, 16), "ONE LABEL", fill=0, font=font)
    draw.text((16, 44), f'{inches_w:.2f}" × {inches_h:.2f}"  ·  {width} × {height} dots', fill=0, font=small)
    draw.text((16, height - 36), "If this box crosses a gap, calibrate media.", fill=0, font=small)

    margin = 16
    y = 78
    draw.text((margin, y), "1 / 2 / 3 / 4 dot strokes", fill=0, font=small)
    y += 24
    for thickness in (1, 2, 3, 4):
        draw.line((margin, y, width - margin, y), fill=0, width=thickness)
        y += 14 + thickness

    y += 10
    x = margin
    for thickness in (1, 2, 3, 4):
        draw.line((x, y, x, y + 40), fill=0, width=thickness)
        x += 56

    y += 56
    checker = 12
    box = min(width - margin * 2, 144)
    for row in range(box // checker):
        for col in range(box // checker):
            if (row + col) % 2 == 0:
                left = margin + col * checker
                top = y + row * checker
                draw.rectangle((left, top, left + checker - 1, top + checker - 1), fill=0)

    return _to_one_bit(gray, "threshold", 128)


def _font(size: int):
    for name in ("arial.ttf", "segoeui.ttf", "calibri.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()
