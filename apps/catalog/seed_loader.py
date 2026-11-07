"""Загрузка исходного каталога из apps/catalog/seed/catalog.json (компактный формат прайса) в БД."""
from __future__ import annotations

import json
from pathlib import Path

from django.core.files import File
from django.db import transaction

from . import catalog_io
from .models import Color, Motorcycle, OptionDef, Photo, SiteSettings

SEED_DIR = Path(__file__).resolve().parent / "seed"


def expand_model(raw: dict, seed: dict) -> dict:
    """Компактная запись прайса → канонический словарь catalog_io. Вход не изменяется."""
    specs = {**seed[f"specs_{raw['specs_base']}"], **raw.get("specs", {})}
    options = {**seed["option_sets"].get(raw.get("options_set", ""), {}), **raw.get("options", {}),
               **raw.get("options_extra", {})}
    variants = [
        {"label": v[0], "battery_ah": v[1], "price_usd": v[2], **(v[3] if len(v) > 3 else {})}
        for v in raw["variants"]
    ]
    return {
        "slug": raw["slug"], "name": raw["name"], "line": raw.get("line", ""), "type": raw["type"],
        "published": raw.get("published", True), "popular": raw.get("popular", False), "sort": raw.get("sort", 100),
        "short": raw.get("short", ""), "description": raw.get("description", ""), "features": raw.get("features", []),
        "specs": specs, "variants": variants, "options": options, "colors": "all",
    }


def load_seed(path: Path | None = None) -> dict:
    return json.loads((path or SEED_DIR / "catalog.json").read_text(encoding="utf-8"))


@transaction.atomic
def seed_catalog(path: Path | None = None, with_photos: bool = True) -> int:
    seed = load_seed(path)
    SiteSettings.load()
    for index, item in enumerate(seed["option_defs"]):
        OptionDef.objects.update_or_create(code=item["code"], defaults={
            "name": item["name"], "description": item.get("description", ""), "sort_order": item.get("sort", index)})
    for index, item in enumerate(seed["colors"]):
        Color.objects.update_or_create(code=item["code"], defaults={
            "name": item["name"], "hex": item["hex"], "sort_order": index * 10})
    codes = set(OptionDef.objects.values_list("code", flat=True))
    models = [catalog_io.normalize_model(expand_model(raw, seed), codes) for raw in seed["models"]]
    count = catalog_io.apply(models)
    if with_photos:
        attach_seed_photos()
    return count


def attach_seed_photos() -> int:
    attached = 0
    for moto in Motorcycle.objects.filter(photos__isnull=True):
        source = SEED_DIR / "photos" / f"{moto.slug}.webp"
        if not source.is_file():
            continue
        with source.open("rb") as handle:
            photo = Photo(motorcycle=moto, alt=f"Электромотоцикл {moto.name}, вид сбоку")
            photo.image.save(f"{moto.slug}.webp", File(handle), save=False)
            photo.save()
        attached += 1
    return attached
