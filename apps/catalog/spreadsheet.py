"""Чтение и запись таблиц каталога (Excel .xlsx и CSV). Одна строка = один вариант модели."""
from __future__ import annotations

import csv
import io
import re
import zipfile
from collections import OrderedDict

from openpyxl import Workbook, load_workbook

from .catalog_io import SPEC_FIELDS, CatalogError

MAX_FILE_BYTES = 5 * 1024 * 1024
MAX_ROWS = 2000
MAX_UNZIPPED_BYTES = 50 * 1024 * 1024

MODEL_COLUMNS = (
    ("slug", "Адрес страницы"), ("name", "Модель"), ("line", "Линейка"), ("type", "Тип"),
    ("published", "Опубликована"), ("popular", "Популярная"), ("sort", "Порядок"), ("short", "Коротко"),
    ("description", "Описание"), ("features", "Особенности (через ;)"),
    *((f, f) for f in SPEC_FIELDS),
)
VARIANT_COLUMNS = (
    ("variant_label", "Вариант"), ("battery_ah", "АКБ, А·ч"), ("variant_voltage_v", "Вариант: напряжение"),
    ("variant_motor_power_w", "Вариант: мощность, Вт"), ("variant_drive", "Вариант: привод"),
    ("variant_top_speed_kmh", "Вариант: скорость"), ("variant_range_max_km", "Вариант: запас хода до"),
    ("variant_brakes", "Вариант: тормоза"), ("variant_tyre_rear", "Вариант: задняя шина"), ("price_usd", "Цена, $"),
)
HEADER_KEY = re.compile(r"\[([a-z0-9_:]+)\]\s*$")
TRUE_WORDS = {"1", "да", "yes", "true", "+", "y"}


def _header_key(cell) -> str:
    text = str(cell or "").strip()
    match = HEADER_KEY.search(text)
    return (match.group(1) if match else text).strip().lower()


def _rows_from_xlsx(data: bytes) -> list[list]:
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        if sum(info.file_size for info in archive.infolist()) > MAX_UNZIPPED_BYTES:
            raise CatalogError("Файл Excel слишком большой после распаковки")
    workbook = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    sheet = workbook["Каталог"] if "Каталог" in workbook.sheetnames else workbook.worksheets[0]
    rows = [list(row) for row in sheet.iter_rows(values_only=True, max_row=MAX_ROWS + 1)]
    workbook.close()
    return rows


def _rows_from_csv(data: bytes) -> list[list]:
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = data.decode("cp1251")
    first = text.splitlines()[0] if text else ""
    delimiter = ";" if first.count(";") >= first.count(",") else ","
    return [row for row in csv.reader(io.StringIO(text), delimiter=delimiter)][: MAX_ROWS + 1]


def read_table(data: bytes) -> list[dict]:
    if len(data) > MAX_FILE_BYTES:
        raise CatalogError("Файл больше 5 МБ")
    rows = _rows_from_xlsx(data) if data[:4] == b"PK\x03\x04" else _rows_from_csv(data)
    if not rows:
        raise CatalogError("Пустой файл")
    header = [_header_key(c) for c in rows[0]]
    result = []
    for values in rows[1:]:
        if not any(v not in (None, "") for v in values):
            continue
        result.append({header[i]: values[i] for i in range(min(len(header), len(values))) if header[i]})
    return result


def rows_to_models(rows: list[dict]) -> list[dict]:
    """Группирует строки по slug; поля модели берутся из первой строки модели."""
    grouped: OrderedDict[str, dict] = OrderedDict()
    for number, row in enumerate(rows, start=2):
        slug = str(row.get("slug") or "").strip().lower()
        if not slug:
            raise CatalogError(f"Строка {number}: не заполнен «Адрес страницы» (slug)")
        model = grouped.get(slug)
        if model is None:
            model = {
                "slug": slug, "name": row.get("name"), "line": row.get("line") or "", "type": row.get("type"),
                "published": str(row.get("published") or "").strip().lower() in TRUE_WORDS,
                "popular": str(row.get("popular") or "").strip().lower() in TRUE_WORDS,
                "sort": row.get("sort") or 100, "short": row.get("short") or "",
                "description": row.get("description") or "", "features": row.get("features") or "",
                "specs": {k: row.get(k) for k in SPEC_FIELDS},
                "options": {k[4:]: v for k, v in row.items() if k.startswith("opt:") and v not in (None, "", "-", "нет")},
                "variants": [], "colors": None,
            }
            grouped[slug] = model
        model["variants"].append({
            "label": row.get("variant_label"), "battery_ah": row.get("battery_ah"), "price_usd": row.get("price_usd"),
            **{k[8:]: row.get(k) for k in row if k.startswith("variant_") and k != "variant_label"},
        })
    return list(grouped.values())


def build_workbook(models: list[dict], option_codes: list[tuple[str, str]]) -> bytes:
    """Excel-файл в формате импорта (используется как шаблон и как выгрузка каталога)."""
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Каталог"
    columns = [*MODEL_COLUMNS, *VARIANT_COLUMNS, *((f"opt:{code}", f"Опция: {name}") for code, name in option_codes)]
    sheet.append([f"{title} [{key}]" for key, title in columns])
    for model in models:
        for variant in model["variants"]:
            row = {**{k: model.get(k, "") for k, _ in MODEL_COLUMNS[:10]}, **model["specs"],
                   "variant_label": variant["label"], "battery_ah": variant.get("battery_ah"),
                   "price_usd": variant.get("price_usd"),
                   **{f"variant_{k}": variant.get(k) for k in ("voltage_v", "motor_power_w", "drive", "top_speed_kmh",
                                                             "range_max_km", "brakes", "tyre_rear")},
                   **{f"opt:{c}": model["options"].get(c, "") for c, _ in option_codes}}
            row["features"] = "; ".join(model.get("features", []))
            row["published"] = "да" if model.get("published") else "нет"
            row["popular"] = "да" if model.get("popular") else "нет"
            sheet.append([_cell(row.get(key)) for key, _ in columns])
    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def _cell(value):
    if value is None:
        return ""
    text = str(value)
    return "'" + text if text[:1] in ("=", "+", "@") else value if isinstance(value, (int, float)) else text
