from PIL import Image, ImageDraw

from app.image_pipeline import (
    SHIPPING_ASPECT,
    ProcessSettings,
    _shipping_target_aspect,
    label_crop_for_image,
    process_image,
)
from app.presets import resolve_size


def _letter_with_label(*, landscape: bool) -> Image.Image:
    page = Image.new("RGB", (2550, 3300), (255, 255, 255))
    draw = ImageDraw.Draw(page)
    if landscape:
        box = (375, 1050, 2175, 2250)
    else:
        box = (675, 450, 1875, 2850)
    draw.rectangle(box, fill=(0, 0, 0))
    return page


def _crop_aspect(crop: tuple[float, float, float, float], size: tuple[int, int]) -> float:
    left, top, right, bottom = crop
    width = (right - left) * size[0]
    height = (bottom - top) * size[1]
    return width / height


def test_shipping_target_aspect_portrait():
    crop = (0.25, 0.1, 0.75, 0.9)
    aspect = _shipping_target_aspect(crop, (1000, 2000))
    assert abs(aspect - SHIPPING_ASPECT) < 0.01


def test_shipping_target_aspect_landscape():
    crop = (0.1, 0.3, 0.9, 0.7)
    aspect = _shipping_target_aspect(crop, (2000, 1000))
    assert abs(aspect - (1.0 / SHIPPING_ASPECT)) < 0.01


def test_label_crop_portrait_shipping_label():
    image = _letter_with_label(landscape=False)
    detected = label_crop_for_image(image, filename="chitchats-shipment.pdf")
    aspect = _crop_aspect(detected["crop"], image.size)
    assert detected["label_like"] is True
    assert abs(aspect - SHIPPING_ASPECT) < 0.08


def test_label_crop_landscape_shipping_label():
    image = _letter_with_label(landscape=True)
    detected = label_crop_for_image(image, filename="shipping-label.pdf")
    aspect = _crop_aspect(detected["crop"], image.size)
    assert detected["label_like"] is True
    assert abs(aspect - (1.0 / SHIPPING_ASPECT)) < 0.12


def test_process_image_landscape_on_4x6_rotates_and_fills():
    image = _letter_with_label(landscape=True)
    detected = label_crop_for_image(image, filename="shipping-label.pdf")
    _, _, width_dots, height_dots, _ = resolve_size("4x6", None, None)
    settings = ProcessSettings(
        width_dots=width_dots,
        height_dots=height_dots,
        fit="cover",
        crop=detected["crop"],
    )
    gray, print_image = process_image(image, settings)
    assert gray.size == (width_dots, height_dots)
    assert print_image.size == (width_dots, height_dots)
    pixels = gray.load()
    ink_rows = sum(1 for y in range(height_dots) if any(pixels[x, y] < 240 for x in range(width_dots)))
    assert ink_rows / height_dots >= 0.85
