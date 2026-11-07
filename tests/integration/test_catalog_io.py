"""Нормализация, сравнение и применение каталога (единый формат для seed JSON и Excel/CSV)."""
import copy
from decimal import Decimal

import pytest

from apps.catalog import catalog_io
from apps.catalog.catalog_io import CatalogError, apply, compare, export_models, normalize_model, to_decimal, to_int
from apps.catalog.models import Motorcycle, MotorcycleOption, Variant
from tests.factories import make_color, make_motorcycle, make_motorcycle_option, make_option_def, make_variant

CODES = {"abs", "usb", "alarm"}


def raw_model(**overrides) -> dict:
    data = {
        "slug": "storm-x", "name": "Storm X", "line": "MX", "type": "sport", "published": True, "popular": False,
        "sort": 10, "short": "Быстрый", "description": "Абзац 1\n\nАбзац 2", "features": ["ABS", "LED"],
        "specs": {"motor_power_w": 5000, "drive": "chain", "cooling": "air", "brakes": "Дисковые"},
        "variants": [{"label": "5 kW 100Ah", "battery_ah": 100, "price_usd": "1000"},
                     {"label": "8 kW 150Ah", "battery_ah": 150, "price_usd": "1500.5", "motor_power_w": 8000}],
        "options": {"abs": "150", "usb": "включено"},
    }
    return {**data, **overrides}


class TestConverters:
    @pytest.mark.parametrize("value, expected", [
        ("1000", Decimal("1000.00")), ("1 200,5", Decimal("1200.50")), ("$99.999", Decimal("100.00")),
        ("1 000", Decimal("1000.00")), (7, Decimal("7.00")), (Decimal("1.234"), Decimal("1.23")),
    ])
    def test_to_decimal_parses_human_formats(self, value, expected):
        assert to_decimal(value, "x") == expected

    @pytest.mark.parametrize("value", [None, ""])
    def test_to_decimal_empty_is_none(self, value):
        assert to_decimal(value, "x") is None

    def test_to_decimal_rejects_text(self):
        with pytest.raises(CatalogError, match="не число"):
            to_decimal("дорого", "Цена")

    def test_to_decimal_rejects_negative(self):
        with pytest.raises(CatalogError, match="отрицательной"):
            to_decimal("-1", "Цена")

    @pytest.mark.xfail(reason="BUG: catalog_io.py:59-64 'nan'/'inf' pass Decimal() and then raise uncaught "
                              "decimal.InvalidOperation on compare/quantize instead of CatalogError",
                       strict=True, raises=ArithmeticError)
    @pytest.mark.parametrize("value", ["nan", "inf"])
    def test_to_decimal_rejects_nan_and_infinity(self, value):
        with pytest.raises(CatalogError):
            to_decimal(value, "Цена")

    def test_to_int_truncates(self):
        assert to_int("5 000", "x") == 5000
        assert to_int(None, "x") is None


class TestNormalizeModel:
    def test_happy_path_canonical_shape(self):
        result = normalize_model(raw_model(), CODES)

        assert result["slug"] == "storm-x"
        assert result["type"] == "sport"
        assert result["features"] == ("ABS", "LED")
        assert result["specs"] == {"motor_power_w": 5000, "drive": "chain", "cooling": "air", "brakes": "Дисковые"}
        assert result["variants"][0] == {"label": "5 kW 100Ah", "price_usd": Decimal("1000.00"), "battery_ah": 100}
        assert result["variants"][1]["motor_power_w"] == 8000
        assert result["options"] == {"abs": "150.00", "usb": "included"}
        assert result["colors"] == "all"

    def test_does_not_mutate_input(self):
        raw = raw_model()
        snapshot = copy.deepcopy(raw)

        normalize_model(raw, CODES)

        assert raw == snapshot

    def test_slug_is_trimmed_and_lowercased(self):
        assert normalize_model(raw_model(slug="  Storm-X "), CODES)["slug"] == "storm-x"

    @pytest.mark.parametrize("missing", ["slug", "name"])
    def test_missing_slug_or_name(self, missing):
        raw = raw_model()
        del raw[missing]
        with pytest.raises(CatalogError, match="обязательны slug и name"):
            normalize_model(raw, CODES)

    def test_blank_slug(self):
        with pytest.raises(CatalogError):
            normalize_model(raw_model(slug="   "), CODES)

    def test_negative_variant_price(self):
        raw = raw_model(variants=[{"label": "A", "battery_ah": 100, "price_usd": "-5"}])
        with pytest.raises(CatalogError, match="вариант 1, цена: цена не может быть отрицательной"):
            normalize_model(raw, CODES)

    def test_negative_option_price(self):
        with pytest.raises(CatalogError, match="опция abs"):
            normalize_model(raw_model(options={"abs": "-10"}), CODES)

    def test_unknown_option(self):
        with pytest.raises(CatalogError, match="неизвестная опция «turbo»"):
            normalize_model(raw_model(options={"turbo": "10"}), CODES)

    @pytest.mark.parametrize("field, value", [("type", "scooter"), ("type", "")])
    def test_bad_type(self, field, value):
        with pytest.raises(CatalogError, match="недопустимое значение"):
            normalize_model(raw_model(**{field: value}), CODES)

    def test_bad_spec_choice(self):
        raw = raw_model(specs={"drive": "кардан"})
        with pytest.raises(CatalogError, match="drive"):
            normalize_model(raw, CODES)

    def test_bad_int_spec(self):
        with pytest.raises(CatalogError, match="motor_power_w"):
            normalize_model(raw_model(specs={"motor_power_w": "много"}), CODES)

    def test_no_variants(self):
        with pytest.raises(CatalogError, match="хотя бы один вариант"):
            normalize_model(raw_model(variants=[]), CODES)

    def test_variant_without_label(self):
        with pytest.raises(CatalogError, match="нет названия варианта"):
            normalize_model(raw_model(variants=[{"label": " ", "battery_ah": 100}]), CODES)

    def test_variant_without_battery(self):
        with pytest.raises(CatalogError, match="ёмкость АКБ"):
            normalize_model(raw_model(variants=[{"label": "A", "price_usd": "1"}]), CODES)

    def test_variant_price_empty_means_on_request(self):
        raw = raw_model(variants=[{"label": "A", "battery_ah": "100", "price_usd": ""}])
        assert normalize_model(raw, CODES)["variants"][0]["price_usd"] is None

    def test_russian_aliases(self):
        raw = raw_model(type="Спорт", specs={"drive": "Цепь", "cooling": "жидкостное"},
                        variants=[{"label": "A", "battery_ah": 100, "drive": "ремень"}])

        result = normalize_model(raw, CODES)

        assert result["type"] == "sport"
        assert result["specs"]["drive"] == "chain"
        assert result["specs"]["cooling"] == "liquid"
        assert result["variants"][0]["drive"] == "belt"

    @pytest.mark.parametrize("alias, expected", [("нейкед", "naked"), ("круизер", "cruiser"), ("туринг", "touring"),
                                                 ("NAKED", "naked")])
    def test_type_aliases(self, alias, expected):
        assert normalize_model(raw_model(type=alias), CODES)["type"] == expected

    def test_water_cooling_alias(self):
        assert normalize_model(raw_model(specs={"cooling": "водяное"}), CODES)["specs"]["cooling"] == "liquid"

    @pytest.mark.parametrize("word", ["включено", "Включено", "входит", "да", "included", "INCL", " вкл "])
    def test_included_words(self, word):
        assert normalize_model(raw_model(options={"abs": word}), CODES)["options"]["abs"] == "included"

    def test_features_from_semicolon_string(self):
        result = normalize_model(raw_model(features="ABS; LED ;; круиз"), CODES)
        assert result["features"] == ("ABS", "LED", "круиз")

    def test_defaults(self):
        raw = {"slug": "a", "name": "A", "variants": [{"label": "v", "battery_ah": 1}]}

        result = normalize_model(raw, set())

        assert result["type"] == "sport"
        assert result["published"] is False
        assert result["sort"] == 100
        assert result["specs"] == {}
        assert result["options"] == {}

    def test_empty_spec_values_skipped(self):
        assert normalize_model(raw_model(specs={"brakes": "", "voltage_v": None}), CODES)["specs"] == {}

    @pytest.mark.xfail(reason="BUG: catalog_io.py:108 empty option value is normalised to the string 'None'; "
                              "apply() then crashes at catalog_io.py:225 Decimal('None')", strict=True)
    @pytest.mark.django_db
    def test_empty_option_value_is_rejected_or_skipped(self):
        make_option_def(code="abs")
        normalized = normalize_model(raw_model(options={"abs": ""}), {"abs"})

        assert normalized["options"].get("abs") != "None"
        apply([normalized])


@pytest.mark.django_db
class TestCompare:
    def _seed(self):
        make_option_def(code="abs")
        make_option_def(code="usb")
        apply([normalize_model(raw_model(), CODES)])

    def test_new_model(self):
        report = compare([normalize_model(raw_model(), CODES)])

        assert report.changes[0].status == "new"
        assert report.missing == ()
        assert report.ok is True

    def test_unchanged(self):
        self._seed()

        report = compare([normalize_model(raw_model(), CODES)])

        assert report.changes[0].status == "unchanged"
        assert report.changes[0].changes == ()

    def test_changed_name_spec_price_and_options(self):
        self._seed()
        raw = raw_model(name="Storm X2", specs={**raw_model()["specs"], "motor_power_w": 6000},
                        options={"abs": "200"})
        raw["variants"] = [{**raw["variants"][0], "price_usd": "1100"}, raw["variants"][1]]

        change = compare([normalize_model(raw, CODES)]).changes[0]

        assert change.status == "changed"
        joined = "\n".join(change.changes)
        assert "motor_power_w: «5000» → «6000»" in joined
        assert "name: «Storm X» → «Storm X2»" in joined
        assert "варианты/цены изменены" in joined
        assert "опции изменены" in joined

    def test_missing_models_listed(self):
        self._seed()
        make_motorcycle(slug="old-one")

        report = compare([normalize_model(raw_model(), CODES)])

        assert report.missing == ("old-one",)

    def test_mixed_report(self):
        self._seed()
        new = normalize_model(raw_model(slug="brand-new", name="New"), CODES)

        report = compare([normalize_model(raw_model(), CODES), new])

        assert [c.status for c in report.changes] == ["unchanged", "new"]

    @pytest.mark.xfail(reason="BUG: catalog_io.py:162,176 compare() only looks at variant label+price; a changed "
                              "battery_ah/variant spec is reported 'unchanged' although apply() overwrites it",
                       strict=True)
    def test_variant_battery_change_is_reported(self):
        self._seed()
        raw = raw_model()
        raw["variants"] = [{**raw["variants"][0], "battery_ah": 120}, raw["variants"][1]]

        assert compare([normalize_model(raw, CODES)]).changes[0].status == "changed"


@pytest.mark.django_db
class TestApply:
    def test_creates_model_variants_options_and_all_colors(self):
        make_option_def(code="abs")
        make_option_def(code="usb")
        red, black = make_color(code="red"), make_color(code="black")

        count = apply([normalize_model(raw_model(), CODES)])

        assert count == 1
        moto = Motorcycle.objects.get(slug="storm-x")
        assert moto.is_published is True
        assert moto.features == "ABS\nLED"
        assert moto.motor_power_w == 5000
        assert [(v.label, v.price_usd, v.sort_order) for v in moto.variants.all()] == [
            ("5 kW 100Ah", Decimal("1000.00"), 10), ("8 kW 150Ah", Decimal("1500.50"), 20)]
        assert moto.variants.get(label="8 kW 150Ah").motor_power_w == 8000
        options = {o.option.code: (o.status, o.price_usd) for o in moto.options.all()}
        assert options == {"abs": ("optional", Decimal("150.00")), "usb": ("included", None)}
        assert set(moto.colors.all()) == {red, black}

    def test_updates_and_removes_variants_absent_from_file(self):
        moto = make_motorcycle(slug="storm-x", name="Old")
        stale = make_variant(moto, label="Old variant")
        kept = make_variant(moto, label="5 kW 100Ah", voltage_v=60, price_usd=Decimal("1"))
        make_option_def(code="abs")
        make_option_def(code="usb")

        apply([normalize_model(raw_model(), CODES)])

        moto.refresh_from_db()
        assert moto.name == "Storm X"
        assert not Variant.objects.filter(pk=stale.pk).exists()
        kept.refresh_from_db()
        assert kept.price_usd == Decimal("1000.00")
        assert kept.voltage_v is None, "переопределение, которого нет в файле, сбрасывается"
        assert moto.variants.count() == 2

    def test_options_sync_updates_status_and_removes_absent(self):
        moto = make_motorcycle(slug="storm-x")
        abs_opt, _usb, alarm = make_option_def(code="abs"), make_option_def(code="usb"), make_option_def(code="alarm")
        make_motorcycle_option(moto, abs_opt, status="included", price_usd=None)
        make_motorcycle_option(moto, alarm, price_usd=Decimal("10"))

        apply([normalize_model(raw_model(), CODES)])

        options = {o.option.code: (o.status, o.price_usd) for o in moto.options.all()}
        assert options == {"abs": ("optional", Decimal("150.00")), "usb": ("included", None)}

    def test_colors_list_filters_known_codes(self):
        make_option_def(code="abs")
        make_option_def(code="usb")
        red = make_color(code="red")
        make_color(code="black")
        normalized = normalize_model(raw_model(colors=["red", "pink"]), CODES)

        apply([normalized])

        assert list(Motorcycle.objects.get(slug="storm-x").colors.all()) == [red]

    def test_update_publication_false_keeps_flags(self):
        moto = make_motorcycle(slug="storm-x", is_published=False, is_popular=True)
        make_option_def(code="abs")
        make_option_def(code="usb")

        apply([normalize_model(raw_model(published=True, popular=False), CODES)], update_publication=False)

        moto.refresh_from_db()
        assert moto.is_published is False
        assert moto.is_popular is True

    def test_does_not_delete_models_missing_from_file(self):
        make_motorcycle(slug="keep-me")
        make_option_def(code="abs")
        make_option_def(code="usb")

        apply([normalize_model(raw_model(), CODES)])

        assert Motorcycle.objects.filter(slug="keep-me").exists()

    def test_apply_is_atomic(self):
        make_option_def(code="abs")
        make_option_def(code="usb")
        good = normalize_model(raw_model(), CODES)
        bad = normalize_model(raw_model(slug="bad", options={"alarm": "5"}), CODES)  # alarm нет в БД

        with pytest.raises(KeyError):
            apply([good, bad])

        assert not Motorcycle.objects.exists()

    def test_export_models_shape(self):
        moto = make_motorcycle(slug="m1", features="A\nB")
        make_variant(moto, label="V", price_usd=None)
        make_motorcycle_option(moto, make_option_def(code="abs"), status=MotorcycleOption.Status.INCLUDED,
                               price_usd=None)

        exported = export_models()[0]

        assert exported["slug"] == "m1"
        assert exported["features"] == ["A", "B"]
        assert set(exported["specs"]) == set(catalog_io.SPEC_FIELDS)
        assert exported["variants"][0]["price_usd"] is None
        assert exported["options"] == {"abs": "включено"}
