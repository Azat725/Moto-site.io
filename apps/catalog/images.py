"""Нормализация загружаемых фото: проверка формата, ограничение размера, перекодирование в WebP без EXIF."""
from __future__ import annotations

import io
import secrets

from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import InMemoryUploadedFile
from PIL import Image, ImageOps, UnidentifiedImageError

ALLOWED_FORMATS = {"JPEG", "PNG", "WEBP"}
MAX_PIXELS = 40_000_000
MAX_SIDE = 1800
MAX_BYTES = 10 * 1024 * 1024


def check_image(upload) -> None:
    """Бросает ValidationError, если файл не JPEG/PNG/WebP разумного размера."""
    if getattr(upload, "size", 0) > MAX_BYTES:
        raise ValidationError("Файл больше 10 МБ.")
    try:
        upload.seek(0)
        with Image.open(upload) as probe:
            if probe.format not in ALLOWED_FORMATS:
                raise ValidationError("Допустимы только JPEG, PNG или WebP.")
            if probe.width * probe.height > MAX_PIXELS:
                raise ValidationError("Слишком большое разрешение изображения.")
    except (UnidentifiedImageError, OSError) as exc:
        raise ValidationError("Файл не является изображением.") from exc
    finally:
        upload.seek(0)


def normalize_upload(field_file):
    """Новый файл WebP (макс. сторона 1800 px, без метаданных; прозрачность сохраняется)."""
    upload = field_file.file
    check_image(upload)
    with Image.open(upload) as probe:
        image = ImageOps.exif_transpose(probe)
        image = image.convert("RGBA" if "A" in image.getbands() or image.mode == "P" else "RGB")

    image.thumbnail((MAX_SIDE, MAX_SIDE))
    buffer = io.BytesIO()
    image.save(buffer, format="WEBP", quality=82, method=6)
    buffer.seek(0)
    name = f"{secrets.token_hex(8)}.webp"
    return InMemoryUploadedFile(buffer, "image", name, "image/webp", buffer.getbuffer().nbytes, None)
