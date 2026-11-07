"""Единый формат каталога (seed JSON, импорт Excel/CSV): нормализация, сравнение с БД и применение.

Модель описывается словарём:
  {slug, name, line, type, published, popular, sort, short, description, features: [..],
   specs: {motor_power_w, ..., tyre_kind}, variants: [{label, battery_ah, price_usd, ...переопределения}],
   options: {code: "included" | "123.45"}, colors: [codes] | "all"}
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation

from django.db import transaction

from .models import Color, Motorcycle, MotorcycleOption, OptionDef, Variant

SPEC_FIELDS = ("motor_power_w", "motor_layout", "drive", "cooling", "voltage_v", "battery_type", "top_speed_kmh",
               "range_min_km", "range_max_km", "brakes", "suspension_front", "suspension_rear", "tyre_front",
               "tyre_rear", "tyre_kind")
INT_SPECS = {"motor_power_w", "voltage_v", "top_speed_kmh", "range_min_km", "range_max_km"}
VARIANT_FIELDS = ("battery_ah", "voltage_v", "motor_power_w", "drive", "top_speed_kmh", "range_max_km", "brakes",
                  "tyre_rear")
VARIANT_INT = {"battery_ah", "voltage_v", "motor_power_w", "top_speed_kmh", "range_max_km"}
CHOICE_ALIASES = {
    "type": {"спорт": "sport", "нейкед": "naked", "круизер": "cruiser", "туринг": "touring"},
    "drive": {"цепь": "chain", "ремень": "belt"},
    "cooling": {"воздушное": "air", "жидкостное": "liquid", "водяное": "liquid"},
}
SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
INCLUDED_WORDS = {"included", "incl", "включено", "входит", "вкл", "да"}


class CatalogError(ValueError):
    pass


@dataclass(frozen=True)
class ModelChange:
    slug: str
    name: str
    status: str  # new | changed | unchanged
    changes: tuple[str, ...] = ()


@dataclass(frozen=True)
class CatalogReport:
    changes: tuple[ModelChange, ...]
    missing: tuple[str, ...]
    errors: tuple[str, ...] = field(default=())

    @property
    def ok(self) -> bool:
        return not self.errors


def to_decimal(value, where: str) -> Decimal | None:
    if value in (None, ""):
        return None
    try:
        number = Decimal(str(value).replace(" ", "").replace(" ", "").replace(",", ".").replace("$", ""))
    except InvalidOperation as exc:
        raise CatalogError(f"{where}: «{value}» — не число") from exc
    if number < 0:
        raise CatalogError(f"{where}: цена не может быть отрицательной")
    return number.quantize(Decimal("0.01"))


def to_int(value, where: str) -> int | None:
    number = to_decimal(value, where)
    return None if number is None else int(number)


def to_choice(kind: str, value, where: str) -> str:
    text = str(value or "").strip().lower()
    allowed = {c for c, _ in {"type": Motorcycle.Type.choices, "drive": Motorcycle.Drive.choices,
                              "cooling": Motorcycle.Cooling.choices}[kind]}
    text = CHOICE_ALIASES[kind].get(text, text)
    if text not in allowed:
        raise CatalogError(f"{where}: недопустимое значение «{value}» для поля {kind}")
    return text


def normalize_model(raw: dict, option_codes: set[str]) -> dict:
    """Проверяет и приводит словарь модели к каноническому виду. Не изменяет вход."""
    slug = str(raw.get("slug", "")).strip().lower()
    where = f"Модель {slug or raw.get('name', '?')}"
    if not slug or not raw.get("name"):
        raise CatalogError(f"{where}: обязательны slug и name")
    if len(slug) > 60 or not SLUG_RE.match(slug):
        raise CatalogError(f"{where}: адрес страницы (slug) — только латиница, цифры и дефисы, до 60 символов")
    if len(str(raw["name"]).strip()) > 60:
        raise CatalogError(f"{where}: название длиннее 60 символов")
    specs_in = raw.get("specs", {})
    specs = {}
    for key in SPEC_FIELDS:
        value = specs_in.get(key)
        if value in (None, ""):
            continue
        if key in INT_SPECS:
            specs[key] = to_int(value, f"{where}, {key}")
        elif key in CHOICE_ALIASES:
            specs[key] = to_choice(key, value, where)
        else:
            specs[key] = str(value).strip()
    variants = tuple(_normalize_variant(v, f"{where}, вариант {i + 1}") for i, v in enumerate(raw.get("variants", [])))
    if not variants:
        raise CatalogError(f"{where}: нужен хотя бы один вариант")
    options = {}
    for code, value in (raw.get("options") or {}).items():
        if code not in option_codes:
            raise CatalogError(f"{where}: неизвестная опция «{code}» (добавьте её в справочник опций)")
        text = str(value).strip().lower()
        options[code] = "included" if text in INCLUDED_WORDS else str(to_decimal(value, f"{where}, опция {code}"))
    features = raw.get("features") or []
    if isinstance(features, str):
        features = [f.strip() for f in features.split(";") if f.strip()]
    return {
        "slug": slug, "name": str(raw["name"]).strip(), "line": str(raw.get("line", "")).strip(),
        "type": to_choice("type", raw.get("type", "sport"), where),
        "published": bool(raw.get("published", False)), "popular": bool(raw.get("popular", False)),
        "sort": int(raw.get("sort", 100) or 100), "short": str(raw.get("short", "")).strip(),
        "description": str(raw.get("description", "")).strip(), "features": tuple(features),
        "specs": specs, "variants": variants, "options": options, "colors": raw.get("colors"),
    }


def _normalize_variant(raw: dict, where: str) -> dict:
    label = str(raw.get("label", "")).strip()
    if not label:
        raise CatalogError(f"{where}: нет названия варианта")
    variant = {"label": label, "price_usd": to_decimal(raw.get("price_usd"), f"{where}, цена")}
    for key in VARIANT_FIELDS:
        value = raw.get(key)
        if value in (None, ""):
            continue
        if key in VARIANT_INT:
            variant[key] = to_int(value, f"{where}, {key}")
        elif key == "drive":
            variant[key] = to_choice("drive", value, where)
        else:
            variant[key] = str(value).strip()
    if "battery_ah" not in variant:
        raise CatalogError(f"{where}: не указана ёмкость АКБ")
    return variant


def export_models() -> list[dict]:
    """Текущий каталог в каноническом формате (для выгрузки в Excel)."""
    result = []
    for moto in Motorcycle.objects.prefetch_related("variants", "options__option"):
        result.append({
            "slug": moto.slug, "name": moto.name, "line": moto.line, "type": moto.type,
            "published": moto.is_published, "popular": moto.is_popular, "sort": moto.sort_order,
            "short": moto.short, "description": moto.description, "features": moto.feature_list,
            "specs": {k: getattr(moto, k) for k in SPEC_FIELDS},
            "variants": [{"label": v.label, "price_usd": v.price_usd, **{k: getattr(v, k) for k in VARIANT_FIELDS}}
                         for v in moto.variants.all()],
            "options": {o.option.code: ("включено" if o.is_included else o.price_usd) for o in moto.options.all()},
        })
    return result


def _current_snapshot(moto: Motorcycle) -> dict:
    return {
        "name": moto.name, "line": moto.line, "type": moto.type, "short": moto.short,
        "description": moto.description, "features": tuple(moto.feature_list), "sort": moto.sort_order,
        "published": moto.is_published, "popular": moto.is_popular,
        "specs": {k: getattr(moto, k) for k in SPEC_FIELDS},
        "variants": sorted(_variant_key(v.label, v.price_usd, {k: getattr(v, k) for k in VARIANT_FIELDS})
                           for v in moto.variants.all()),
        "options": {o.option.code: ("included" if o.is_included else str(o.price_usd)) for o in moto.options.all()},
    }


def _variant_key(label: str, price, fields: dict) -> tuple:
    extras = tuple(str(fields.get(k) if fields.get(k) is not None else "") for k in VARIANT_FIELDS)
    return (label, str(price) if price is not None else None, extras)


def compare(models: list[dict]) -> CatalogReport:
    existing = {m.slug: m for m in Motorcycle.objects.prefetch_related("variants", "options__option")}
    changes = []
    for item in models:
        moto = existing.get(item["slug"])
        if moto is None:
            changes.append(ModelChange(item["slug"], item["name"], "new"))
            continue
        old = _current_snapshot(moto)
        new_variants = sorted(_variant_key(v["label"], v["price_usd"], v) for v in item["variants"])
        diffs = [f"{k}: «{old['specs'][k]}» → «{v}»" for k, v in item["specs"].items() if old["specs"].get(k) != v]
        diffs += [f"{k}: «{old[k]}» → «{item[k]}»" for k in ("name", "line", "type", "short", "sort") if old[k] != item[k]]
        diffs += [f"{k} изменено" for k in ("description", "features") if old[k] != item[k]]
        diffs += [f"публикация {k}: {old[k]} → {item[k]}" for k in ("published", "popular") if old[k] != item[k]]
        if old["variants"] != new_variants:
            diffs.append("варианты/цены изменены")
        if old["options"] != item["options"]:
            diffs.append("опции изменены")
        changes.append(ModelChange(item["slug"], item["name"], "changed" if diffs else "unchanged", tuple(diffs)))
    slugs = {m["slug"] for m in models}
    missing = tuple(sorted(s for s in existing if s not in slugs))
    return CatalogReport(tuple(changes), missing)


@transaction.atomic
def apply(models: list[dict], update_publication: bool = True) -> int:
    """Создаёт/обновляет модели, их варианты и опции. Ничего не удаляет, кроме вариантов, которых нет в файле."""
    option_ids = dict(OptionDef.objects.values_list("code", "id"))
    all_colors = list(Color.objects.all())
    for item in models:
        defaults = {"name": item["name"], "line": item["line"], "type": item["type"], "short": item["short"],
                    "description": item["description"], "features": "\n".join(item["features"]),
                    "sort_order": item["sort"], **item["specs"]}
        if update_publication:
            defaults |= {"is_published": item["published"], "is_popular": item["popular"]}
        moto, _ = Motorcycle.objects.update_or_create(slug=item["slug"], defaults=defaults)
        _sync_variants(moto, item["variants"])
        _sync_options(moto, item["options"], option_ids)
        codes = item["colors"]
        if codes is not None:  # нет колонки цветов — выбранные владельцем цвета не трогаем
            moto.colors.set(all_colors if codes == "all" else [c for c in all_colors if c.code in set(codes)])
    return len(models)


def _sync_variants(moto: Motorcycle, variants: tuple[dict, ...]) -> None:
    keep = []
    for order, data in enumerate(variants, start=1):
        blank = {k: (None if k in VARIANT_INT else "") for k in VARIANT_FIELDS if k != "battery_ah"}
        fields = blank | {k: v for k, v in data.items() if k != "label"} | {"sort_order": order * 10}
        variant, _ = Variant.objects.update_or_create(motorcycle=moto, label=data["label"], defaults=fields)
        keep.append(variant.pk)
    moto.variants.exclude(pk__in=keep).delete()


def _sync_options(moto: Motorcycle, options: dict, option_ids: dict) -> None:
    for code, value in options.items():
        included = value == "included"
        MotorcycleOption.objects.update_or_create(
            motorcycle=moto, option_id=option_ids[code],
            defaults={"status": "included" if included else "optional",
                      "price_usd": None if included else Decimal(value)},
        )
    moto.options.exclude(option__code__in=list(options)).delete()
