from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from typing import Literal

from PIL import Image, ImageFilter, ImageOps

FitMode = Literal["contain", "cover", "stretch"]
DitherMode = Literal["floyd", "atkinson", "threshold"]


@dataclass(frozen=True)
class ProcessSettings:
    width_dots: int
    height_dots: int
    fit: FitMode = "cover"
    dither: DitherMode = "floyd"
    contrast: float = 1.2
    threshold: int = 128
    sharpen: bool = True


def load_image(data: bytes) -> Image.Image:
    image = Image.open(BytesIO(data))
    image.load()
    return _flatten_to_rgb(image)


def process_image(source: Image.Image, settings: ProcessSettings) -> tuple[Image.Image, Image.Image]:
    """Return (resized grayscale, 1-bit print image)."""
    gray = ImageOps.grayscale(source)
    gray = _apply_contrast(gray, settings.contrast)
    if settings.sharpen:
        gray = gray.filter(ImageFilter.UnsharpMask(radius=1.2, percent=140, threshold=2))
    gray = _fit_to_label(gray, settings.width_dots, settings.height_dots, settings.fit)
    print_image = _to_one_bit(gray, settings.dither, settings.threshold)
    return gray, print_image


def image_to_png_bytes(image: Image.Image) -> bytes:
    output = BytesIO()
    save_image = image
    if image.mode == "1":
        save_image = image.convert("L")
    save_image.save(output, format="PNG")
    return output.getvalue()


def _flatten_to_rgb(image: Image.Image) -> Image.Image:
    if image.mode in {"RGBA", "LA"} or (image.mode == "P" and "transparency" in image.info):
        rgba = image.convert("RGBA")
        background = Image.new("RGB", rgba.size, (255, 255, 255))
        background.paste(rgba, mask=rgba.getchannel("A"))
        return background
    return image.convert("RGB")


def _apply_contrast(image: Image.Image, contrast: float) -> Image.Image:
    contrast = max(0.2, min(4.0, float(contrast)))
    if abs(contrast - 1.0) < 0.01:
        return image

    def _map(value: int) -> int:
        mapped = 128 + (value - 128) * contrast
        return max(0, min(255, int(mapped)))

    return image.point(_map)


def _fit_to_label(image: Image.Image, width: int, height: int, fit: FitMode) -> Image.Image:
    if fit == "stretch":
        return image.resize((width, height), Image.Resampling.LANCZOS)

    src_w, src_h = image.size
    if src_w == 0 or src_h == 0:
        return Image.new("L", (width, height), 255)

    scale_w = width / src_w
    scale_h = height / src_h

    if fit == "cover":
        scale = max(scale_w, scale_h)
        resized = image.resize(
            (max(1, round(src_w * scale)), max(1, round(src_h * scale))),
            Image.Resampling.LANCZOS,
        )
        left = max(0, (resized.width - width) // 2)
        top = max(0, (resized.height - height) // 2)
        return resized.crop((left, top, left + width, top + height))

    scale = min(scale_w, scale_h)
    resized = image.resize(
        (max(1, round(src_w * scale)), max(1, round(src_h * scale))),
        Image.Resampling.LANCZOS,
    )
    canvas = Image.new("L", (width, height), 255)
    left = (width - resized.width) // 2
    top = (height - resized.height) // 2
    canvas.paste(resized, (left, top))
    return canvas


def _to_one_bit(gray: Image.Image, dither: DitherMode, threshold: int) -> Image.Image:
    if dither == "threshold":
        cutoff = max(0, min(255, int(threshold)))
        return gray.point(lambda value: 0 if value < cutoff else 255, mode="1")
    if dither == "atkinson":
        return _atkinson_dither(gray)
    return gray.convert("1", dither=Image.Dither.FLOYDSTEINBERG)


def _atkinson_dither(gray: Image.Image) -> Image.Image:
    width, height = gray.size
    pixels = [float(value) for value in gray.getdata()]

    for y in range(height):
        row = y * width
        for x in range(width):
            index = row + x
            old = pixels[index]
            new = 0.0 if old < 128 else 255.0
            pixels[index] = new
            error = (old - new) / 8.0
            neighbors = (
                (x + 1, y),
                (x + 2, y),
                (x - 1, y + 1),
                (x, y + 1),
                (x + 1, y + 1),
                (x, y + 2),
            )
            for nx, ny in neighbors:
                if 0 <= nx < width and 0 <= ny < height:
                    pixels[ny * width + nx] += error

    out = Image.new("1", (width, height))
    out.putdata([0 if value < 128 else 255 for value in pixels])
    return out
