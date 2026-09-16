from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from typing import Literal

from PIL import Image, ImageFilter, ImageOps

PDF_RENDER_DPI = 406
MAX_PDF_RENDER_PX = 4500
SHIPPING_PRESET = "4x6"
SHIPPING_ASPECT = 4.0 / 6.0

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
    crop: tuple[float, float, float, float] = (0.0, 0.0, 1.0, 1.0)


def is_pdf(data: bytes, filename: str = "") -> bool:
    return data[:5] == b"%PDF-" or filename.lower().endswith(".pdf")


def pdf_page_count(data: bytes) -> int:
    import pypdfium2 as pdfium

    pdf = pdfium.PdfDocument(data)
    try:
        return len(pdf)
    finally:
        pdf.close()


def render_pdf_page(data: bytes, page: int = 1, dpi: float = PDF_RENDER_DPI) -> Image.Image:
    import pypdfium2 as pdfium

    pdf = pdfium.PdfDocument(data)
    try:
        count = len(pdf)
        if count < 1:
            raise ValueError("PDF has no pages")
        index = max(0, min(count - 1, int(page) - 1))
        pdf_page = pdf[index]
        width_pt, height_pt = pdf_page.get_size()
        scale = float(dpi) / 72.0
        longest = max(width_pt, height_pt) * scale
        if longest > MAX_PDF_RENDER_PX:
            scale *= MAX_PDF_RENDER_PX / longest
        bitmap = pdf_page.render(scale=scale)
        image = bitmap.to_pil()
    finally:
        pdf.close()
    return _flatten_to_rgb(image)


def load_image(data: bytes, *, page: int = 1, filename: str = "") -> Image.Image:
    if is_pdf(data, filename):
        return render_pdf_page(data, page)
    image = Image.open(BytesIO(data))
    image.load()
    return _flatten_to_rgb(image)


def normalize_crop(crop: tuple[float, float, float, float]) -> tuple[float, float, float, float]:
    left, top, right, bottom = crop
    left = max(0.0, min(1.0, float(left)))
    top = max(0.0, min(1.0, float(top)))
    right = max(0.0, min(1.0, float(right)))
    bottom = max(0.0, min(1.0, float(bottom)))
    if right < left:
        left, right = right, left
    if bottom < top:
        top, bottom = bottom, top
    if right - left < 0.02:
        right = min(1.0, left + 0.02)
        left = max(0.0, right - 0.02)
    if bottom - top < 0.02:
        bottom = min(1.0, top + 0.02)
        top = max(0.0, bottom - 0.02)
    return left, top, right, bottom


def detect_content_crop(image: Image.Image) -> tuple[float, float, float, float]:
    """Normalized crop around ink so a 4×6 label on letter paper is isolated."""
    gray = ImageOps.grayscale(image)
    work = gray
    scale = 1.0
    longest = max(gray.size)
    if longest > 900:
        scale = 900 / longest
        work = gray.resize(
            (max(1, round(gray.width * scale)), max(1, round(gray.height * scale))),
            Image.Resampling.BILINEAR,
        )
    mask = work.point(lambda value: 255 if value < 240 else 0)
    box = mask.getbbox()
    if box is None:
        return (0.0, 0.0, 1.0, 1.0)

    left, top, right, bottom = (coord / scale for coord in box)
    width, height = gray.size
    pad = max(2.0, 0.006 * max(width, height))
    left = max(0.0, left - pad)
    top = max(0.0, top - pad)
    right = min(float(width), right + pad)
    bottom = min(float(height), bottom + pad)
    crop = normalize_crop((left / width, top / height, right / width, bottom / height))
    area = (crop[2] - crop[0]) * (crop[3] - crop[1])
    if area >= 0.88:
        return (0.0, 0.0, 1.0, 1.0)
    return crop


def _shipping_target_aspect(
    crop: tuple[float, float, float, float],
    size: tuple[int, int],
) -> float:
    """Pick portrait 4:6 or landscape 6:4 based on detected ink box orientation."""
    left, top, right, bottom = normalize_crop(crop)
    img_w, img_h = size
    box_w = max(2.0, (right - left) * img_w)
    box_h = max(2.0, (bottom - top) * img_h)
    aspect = box_w / box_h if box_h else SHIPPING_ASPECT
    landscape = 1.0 / SHIPPING_ASPECT
    if abs(aspect - landscape) < abs(aspect - SHIPPING_ASPECT):
        return landscape
    return SHIPPING_ASPECT


def expand_crop_to_aspect(
    crop: tuple[float, float, float, float],
    size: tuple[int, int],
    target_aspect: float,
) -> tuple[float, float, float, float]:
    left, top, right, bottom = normalize_crop(crop)
    img_w, img_h = size
    if img_w < 2 or img_h < 2 or target_aspect <= 0:
        return left, top, right, bottom

    box_w = max(2.0, (right - left) * img_w)
    box_h = max(2.0, (bottom - top) * img_h)
    current = box_w / box_h
    if current < target_aspect:
        box_w = box_h * target_aspect
    else:
        box_h = box_w / target_aspect

    frac_w = box_w / img_w
    frac_h = box_h / img_h
    if frac_w > 1:
        frac_h *= 1 / frac_w
        frac_w = 1.0
    if frac_h > 1:
        frac_w *= 1 / frac_h
        frac_h = 1.0

    center_x = (left + right) / 2
    center_y = (top + bottom) / 2
    left = min(max(0.0, center_x - frac_w / 2), 1.0 - frac_w)
    top = min(max(0.0, center_y - frac_h / 2), 1.0 - frac_h)
    return normalize_crop((left, top, left + frac_w, top + frac_h))


def suggest_label_preset(
    image: Image.Image,
    crop: tuple[float, float, float, float],
    filename: str = "",
) -> str | None:
    left, top, right, bottom = normalize_crop(crop)
    width = (right - left) * image.width
    height = (bottom - top) * image.height
    if width < 8 or height < 8:
        return None

    aspect = width / height
    name = filename.lower()
    shipping_name = any(
        token in name
        for token in (
            "shipment",
            "shipping",
            "postage",
            "usps",
            "ups",
            "fedex",
            "chit",
            "label",
        )
    )
    is_4x6 = abs(aspect - SHIPPING_ASPECT) <= 0.08 or abs(aspect - (1 / SHIPPING_ASPECT)) <= 0.12
    if is_4x6 or shipping_name:
        return SHIPPING_PRESET
    return None


def label_crop_for_image(image: Image.Image, filename: str = "") -> dict:
    crop = detect_content_crop(image)
    suggested = suggest_label_preset(image, crop, filename)
    if suggested == SHIPPING_PRESET:
        crop = expand_crop_to_aspect(crop, image.size, _shipping_target_aspect(crop, image.size))
    return {
        "crop": crop,
        "suggested_preset": suggested,
        "label_like": suggested == SHIPPING_PRESET,
    }


def apply_crop(image: Image.Image, crop: tuple[float, float, float, float]) -> Image.Image:
    left, top, right, bottom = normalize_crop(crop)
    if (left, top, right, bottom) == (0.0, 0.0, 1.0, 1.0):
        return image
    width, height = image.size
    box = (
        int(round(left * width)),
        int(round(top * height)),
        int(round(right * width)),
        int(round(bottom * height)),
    )
    if box[2] - box[0] < 2 or box[3] - box[1] < 2:
        return image
    return image.crop(box)


def _maybe_rotate_for_label(source: Image.Image, settings: ProcessSettings) -> Image.Image:
    """Rotate landscape label content 90° when the target stock is portrait."""
    if settings.width_dots >= settings.height_dots:
        return source
    if source.width <= source.height:
        return source
    return source.rotate(90, expand=True, resample=Image.Resampling.BICUBIC)


def process_image(source: Image.Image, settings: ProcessSettings) -> tuple[Image.Image, Image.Image]:
    """Return (resized grayscale, 1-bit print image)."""
    source = apply_crop(source, settings.crop)
    source = _maybe_rotate_for_label(source, settings)
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
