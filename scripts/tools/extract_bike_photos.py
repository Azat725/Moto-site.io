"""Разовый инструмент: вырезает фото мотоциклов из прайс-листа поставщика (PDF из картинок).

Запуск (нужны pymupdf и Pillow):
    python scripts/tools/extract_bike_photos.py --pdf _private/MAICHIEV2026.pdf --out apps/catalog/seed/photos

Номер страницы для каждой модели берётся из поля "photo" в apps/catalog/seed/catalog.json.
Водяной знак поставщика НЕ удаляется (ст. 1300 ГК РФ) — для продакшена запросите у поставщика чистые фото.
В кадр не попадают шапка с контактами поставщика и таблицы.
"""
from __future__ import annotations

import argparse
import io
import json
from pathlib import Path

import pymupdf
from PIL import Image, ImageChops

# Область с фото на странице прайса (доли ширины/высоты): слева под названием модели.
CROP = (0.005, 0.165, 0.303, 0.545)
WIDE = (0.005, 0.165, 0.325, 0.545)  # на этих страницах таблица начинается правее
CROP_OVERRIDES = {"dx250-m": (0.005, 0.165, 0.303, 0.468), **{s: WIDE for s in ("yl-m", "jy-mx", "df-mx", "yl-mx", "hy-mx", "mc-mx")}}
MAX_WIDTH = 1200


def page_image(doc, page_number: int) -> Image.Image:
    page = doc[page_number - 1]
    xref = page.get_images(full=True)[0][0]
    pixmap = pymupdf.Pixmap(doc, xref)
    if pixmap.n - pixmap.alpha > 3:
        pixmap = pymupdf.Pixmap(pymupdf.csRGB, pixmap)
    return Image.open(io.BytesIO(pixmap.tobytes("png"))).convert("RGB")


def trim_white(image: Image.Image, threshold: int = 238, pad: int = 24) -> Image.Image:
    background = Image.new("RGB", image.size, (255, 255, 255))
    diff = ImageChops.difference(image, background).convert("L").point(lambda v: 255 if v > 255 - threshold else 0)
    box = diff.getbbox()
    if not box:
        return image
    left, top, right, bottom = box
    return image.crop((max(left - pad, 0), max(top - pad, 0), min(right + pad, image.width), min(bottom + pad, image.height)))


def extract(pdf: Path, catalog: Path, out: Path) -> list[str]:
    data = json.loads(catalog.read_text(encoding="utf-8"))
    out.mkdir(parents=True, exist_ok=True)
    doc = pymupdf.open(pdf)
    saved = []
    for model in data["models"]:
        number = model.get("photo")
        if not number:
            continue
        image = page_image(doc, number)
        w, h = image.size
        box = CROP_OVERRIDES.get(model["slug"], CROP)
        crop = image.crop((int(box[0] * w), int(box[1] * h), int(box[2] * w), int(box[3] * h)))
        crop = trim_white(crop)
        if crop.width > MAX_WIDTH:
            crop = crop.resize((MAX_WIDTH, round(crop.height * MAX_WIDTH / crop.width)), Image.LANCZOS)
        target = out / f"{model['slug']}.webp"
        crop.save(target, "WEBP", quality=84, method=6)
        saved.append(f"{target.name} {crop.width}x{crop.height}")
    return saved


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pdf", required=True, type=Path)
    parser.add_argument("--catalog", default=Path("apps/catalog/seed/catalog.json"), type=Path)
    parser.add_argument("--out", default=Path("apps/catalog/seed/photos"), type=Path)
    args = parser.parse_args()
    for line in extract(args.pdf, args.catalog, args.out):
        print(line)
    print("Напоминание: водяной знак поставщика не удаляется — запросите чистые фото для продакшена.")


if __name__ == "__main__":
    main()
