"""Чтение/запись таблиц каталога: CSV (; , BOM, cp1251) и xlsx, включая полный круг экспорт → импорт."""
import io
from decimal import Decimal

import pytest
from openpyxl import Workbook, load_workbook

from apps.catalog import spreadsheet
from apps.catalog.catalog_io import CatalogError, apply, compare, export_models, normalize_model
from apps.catalog.models import MotorcycleOption
from apps.catalog.spreadsheet import build_workbook, read_table, rows_to_models
from tests.factories import make_motorcycle, make_motorcycle_option, make_option_def, make_variant

CSV_HEADER = "Адрес страницы [slug];Модель [name];Тип [type];Опубликована [published];Вариант [variant_label];" \
             "АКБ, А·ч [battery_ah];Цена, $ [price_usd];Опция: ABS [opt:abs]"
CSV_ROWS = ["storm-x;Storm X;спорт;да;5 kW;100;1000;150", "storm-x;Storm X;спорт;да;8 kW;150;1 500,50;включено"]


def _csv(encoding="utf-8-sig", delimiter=";") -> bytes:
    text = "\r\n".join([CSV_HEADER, *CSV_ROWS]).replace(";", delimiter)
    return text.encode(encoding)


def _xlsx(rows: list[list], title="Каталог") -> bytes:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = title
    for row in rows:
        sheet.append(row)
    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


class TestReadTableCsv:
    def test_semicolon_with_utf8_bom(self):
        data = _csv()
        assert data.startswith(b"\xef\xbb\xbf")

        rows = read_table(data)

        assert rows[0] == {"slug": "storm-x", "name": "Storm X", "type": "спорт", "published": "да",
                           "variant_label": "5 kW", "battery_ah": "100", "price_usd": "1000", "opt:abs": "150"}
        assert rows[1]["price_usd"] == "1 500,50"

    def test_cp1251_fallback(self):
        data = _csv(encoding="cp1251")
        with pytest.raises(UnicodeDecodeError):
            data.decode("utf-8")

        rows = read_table(data)

        assert rows[1]["opt:abs"] == "включено"
        assert rows[0]["type"] == "спорт"

    def test_comma_delimiter_detected(self):
        data = b"slug,name,variant_label,battery_ah\nm1,M1,V,100\n"
        assert read_table(data) == [{"slug": "m1", "name": "M1", "variant_label": "V", "battery_ah": "100"}]

    def test_plain_keys_and_case_insensitive_headers(self):
        assert read_table(b"SLUG;Name\nm1;M1\n") == [{"slug": "m1", "name": "M1"}]

    def test_blank_rows_skipped_and_short_rows_tolerated(self):
        data = b"slug;name;line\n;;\nm1;M1\n\n"
        assert read_table(data) == [{"slug": "m1", "name": "M1"}]

    def test_columns_with_empty_header_dropped(self):
        assert read_table(b"slug;;name\nm1;junk;M1\n") == [{"slug": "m1", "name": "M1"}]

    def test_empty_file_rejected(self):
        with pytest.raises(CatalogError, match="Пустой файл"):
            read_table(b"")

    def test_oversize_file_rejected(self):
        with pytest.raises(CatalogError, match="5 МБ"):
            read_table(b"x" * (spreadsheet.MAX_FILE_BYTES + 1))

    @pytest.mark.xfail(reason="BUG: spreadsheet.py:46,58 rows beyond MAX_ROWS are silently dropped; apply() then "
                              "deletes the variants that were cut off instead of the import being rejected",
                       strict=True)
    def test_too_many_rows_rejected(self, monkeypatch):
        monkeypatch.setattr(spreadsheet, "MAX_ROWS", 2)
        data = b"slug;name\n" + b"".join(b"m%d;M\n" % i for i in range(5))

        with pytest.raises(CatalogError):
            read_table(data)


class TestReadTableXlsx:
    def test_reads_catalog_sheet(self):
        data = _xlsx([["Адрес страницы [slug]", "АКБ [battery_ah]"], ["m1", 100], [None, None]])
        assert read_table(data) == [{"slug": "m1", "battery_ah": 100}]

    def test_falls_back_to_first_sheet(self):
        assert read_table(_xlsx([["slug"], ["m1"]], title="Лист1")) == [{"slug": "m1"}]

    def test_zip_bomb_guard(self, monkeypatch):
        monkeypatch.setattr(spreadsheet, "MAX_UNZIPPED_BYTES", 100)
        with pytest.raises(CatalogError, match="распаковки"):
            read_table(_xlsx([["slug"], ["m1"]]))


class TestRowsToModels:
    def test_groups_variants_by_slug(self):
        models = rows_to_models(read_table(_csv()))

        assert len(models) == 1
        model = models[0]
        assert model["published"] is True and model["popular"] is False
        assert [v["label"] for v in model["variants"]] == ["5 kW", "8 kW"]
        assert model["options"] == {"abs": "150"}, "опции берутся из первой строки модели"
        assert model["colors"] == "all"

    def test_variant_prefixed_columns_map_to_variant_fields(self):
        rows = [{"slug": "m1", "variant_label": "V", "variant_voltage_v": "60", "variant_drive": "ремень"}]
        variant = rows_to_models(rows)[0]["variants"][0]
        assert variant["voltage_v"] == "60" and variant["drive"] == "ремень"

    @pytest.mark.parametrize("value", [None, "", "-", "нет"])
    def test_absent_option_markers_skipped(self, value):
        rows = [{"slug": "m1", "variant_label": "V", "opt:abs": value}]
        assert rows_to_models(rows)[0]["options"] == {}

    @pytest.mark.parametrize("word", ["1", "да", "Yes", "TRUE", "+", "y"])
    def test_true_words(self, word):
        assert rows_to_models([{"slug": "m1", "published": word}])[0]["published"] is True

    def test_missing_slug_reports_row_number(self):
        with pytest.raises(CatalogError, match="Строка 3"):
            rows_to_models([{"slug": "m1"}, {"slug": " "}])

    def test_csv_end_to_end_normalises(self):
        models = rows_to_models(read_table(_csv(encoding="cp1251")))
        normalized = normalize_model(models[0], {"abs"})

        assert normalized["type"] == "sport"
        assert normalized["variants"][1]["price_usd"] == Decimal("1500.50")
        assert normalized["options"] == {"abs": "150.00"}


class TestBuildWorkbook:
    def test_header_has_keys_and_option_columns(self):
        data = build_workbook([], [("abs", "ABS")])

        sheet = load_workbook(io.BytesIO(data))["Каталог"]
        header = [c.value for c in sheet[1]]
        assert header[0] == "Адрес страницы [slug]"
        assert header[-1] == "Опция: ABS [opt:abs]"

    def test_formula_like_text_is_neutralised(self):
        model = {"slug": "m1", "name": "=HYPERLINK(\"http://evil\")", "short": "@cmd", "specs": {},
                 "options": {}, "variants": [{"label": "+V", "battery_ah": 100, "price_usd": None}]}

        data = build_workbook([model], [])

        sheet = load_workbook(io.BytesIO(data))["Каталог"]
        values = [c.value for c in sheet[2]]
        assert "'=HYPERLINK(\"http://evil\")" in values
        assert "'@cmd" in values
        assert "'+V" in values
        assert all(c.data_type != "f" for c in sheet[2])


@pytest.mark.django_db
class TestRoundTrip:
    def _seed(self):
        abs_opt, usb = make_option_def(code="abs", name="ABS"), make_option_def(code="usb", name="USB")
        moto = make_motorcycle(slug="storm-x", name="Storm X", line="MX", short="Быстрый", features="ABS\nLED",
                               type="naked", drive="belt", cooling="liquid")
        make_variant(moto, label="5 kW 100Ah", battery_ah=100, price_usd=Decimal("1000.00"))
        make_variant(moto, label="8 kW 150Ah", battery_ah=150, price_usd=None, motor_power_w=8000, drive="chain")
        make_motorcycle_option(moto, abs_opt, price_usd=Decimal("150.50"))
        make_motorcycle_option(moto, usb, status=MotorcycleOption.Status.INCLUDED, price_usd=None)
        other = make_motorcycle(slug="calm", name="Calm", is_published=False)
        make_variant(other, label="Base", battery_ah=60, price_usd=Decimal("700"))
        return [("abs", "ABS"), ("usb", "USB")]

    def _reimport(self, options):
        data = build_workbook(export_models(), options)
        rows = read_table(data)
        return [normalize_model(raw, {c for c, _ in options}) for raw in rows_to_models(rows)]

    def test_export_import_reports_unchanged(self):
        options = self._seed()

        models = self._reimport(options)
        report = compare(models)

        assert {c.slug: c.status for c in report.changes} == {"storm-x": "unchanged", "calm": "unchanged"}
        assert report.missing == ()

    def test_round_trip_preserves_values(self):
        options = self._seed()

        storm = next(m for m in self._reimport(options) if m["slug"] == "storm-x")

        assert storm["type"] == "naked"
        assert storm["specs"]["drive"] == "belt"
        assert storm["specs"]["cooling"] == "liquid"
        assert storm["published"] is True
        assert storm["features"] == ("ABS", "LED")
        assert storm["options"] == {"abs": "150.50", "usb": "included"}
        assert storm["variants"][1]["price_usd"] is None
        assert storm["variants"][1]["motor_power_w"] == 8000

    def test_reapply_is_idempotent(self):
        options = self._seed()
        models = self._reimport(options)

        apply(models)

        assert all(c.status == "unchanged" for c in compare(self._reimport(options)).changes)

    @pytest.mark.xfail(reason="BUG: spreadsheet.py:131 _cell prefixes text starting with =,+,@ with an apostrophe "
                              "that read_table never strips, so export→import mutates such text", strict=True)
    def test_round_trip_text_starting_with_plus(self):
        options = self._seed()
        from apps.catalog.models import Motorcycle

        Motorcycle.objects.filter(slug="storm-x").update(short="+30% к запасу хода")

        storm = next(m for m in self._reimport(options) if m["slug"] == "storm-x")

        assert storm["short"] == "+30% к запасу хода"
