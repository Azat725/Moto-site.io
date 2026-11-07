"""Предложения и серверный расчёт комплектации с учётом БД."""
from datetime import date
from decimal import Decimal

import pytest

from apps.catalog import pricing
from apps.catalog.models import MotorcycleOption, SiteSettings
from apps.catalog.services import QuoteError, build_offer, current_context, published_motorcycles, quote
from tests.factories import (
    make_full_motorcycle,
    make_motorcycle,
    make_motorcycle_option,
    make_option_def,
    make_rate,
    make_site_settings,
    make_variant,
)

pytestmark = pytest.mark.django_db

CTX = pricing.PriceContext(rate=Decimal("90"), markup_rub=100_000, step=1000)


class TestBuildOffer:
    def test_variant_prices_include_markup_and_round_up(self):
        moto = make_motorcycle()
        v = make_variant(moto, price_usd=Decimal("1000.01"))

        offer = build_offer(moto, CTX)

        # 1000.01 * 90 = 90 000.90 ₽ + 100 000 = 190 000.90 → вверх до 1000 → 191 000
        assert offer.variants[0].id == v.id
        assert offer.variants[0].kopecks == 19_000_090
        assert offer.variants[0].price_rub == 191_000

    def test_price_on_request_variant_is_none(self):
        moto = make_motorcycle()
        make_variant(moto, price_usd=None)

        offer = build_offer(moto, CTX)

        assert offer.variants[0].kopecks is None
        assert offer.variants[0].price_rub is None
        assert offer.min_price_rub is None
        assert offer.max_price_rub is None

    def test_min_and_max_ignore_on_request(self):
        moto = make_motorcycle()
        make_variant(moto, price_usd=Decimal("2000"), sort_order=1)
        make_variant(moto, price_usd=None, sort_order=2)
        make_variant(moto, price_usd=Decimal("1000"), sort_order=3)

        offer = build_offer(moto, CTX)

        assert offer.min_price_rub == 190_000
        assert offer.max_price_rub == 280_000

    def test_included_option_costs_zero_paid_option_in_rub(self):
        moto = make_full_motorcycle()

        offer = build_offer(moto, CTX)
        by_name = {o.name: o for o in offer.options}

        assert by_name["USB"].included is True
        assert by_name["USB"].kopecks == 0
        assert by_name["USB"].plus_rub == 0
        assert by_name["ABS"].included is False
        assert by_name["ABS"].kopecks == 900_000
        assert by_name["ABS"].plus_rub == 9000

    def test_included_option_with_price_still_free(self):
        moto = make_motorcycle()
        make_variant(moto)
        make_motorcycle_option(moto, status=MotorcycleOption.Status.INCLUDED, price_usd=Decimal("500"))

        assert build_offer(moto, CTX).options[0].kopecks == 0

    def test_optional_option_without_price_is_free(self):
        moto = make_motorcycle()
        make_variant(moto)
        make_motorcycle_option(moto, price_usd=None)

        option = build_offer(moto, CTX).options[0]
        assert option.kopecks == 0 and option.plus_rub == 0

    def test_option_plus_rub_rounds_up_to_ruble(self):
        moto = make_motorcycle()
        make_variant(moto)
        make_motorcycle_option(moto, price_usd=Decimal("0.01"))  # 0.90 ₽

        assert build_offer(moto, CTX).options[0].plus_rub == 1

    def test_no_variants_gives_empty_offer(self):
        offer = build_offer(make_motorcycle(), CTX)
        assert offer.variants == ()
        assert offer.min_price_rub is None

    def test_as_json_exposes_only_rub_components(self):
        moto = make_full_motorcycle()

        data = build_offer(moto, CTX).as_json()

        assert data["step"] == 1000
        assert {"id", "label", "kop"} == set(data["variants"][0])
        assert {"code", "kop", "included"} == set(data["options"][0])
        flat = repr(data)
        assert "price_usd" not in flat and "markup" not in flat


class TestQuote:
    def test_total_for_variant_and_paid_option(self):
        moto = make_full_motorcycle()
        variant = moto.variants.get(label="5 kW 100Ah")

        result = quote(moto, CTX, variant.id, [f"abs_{moto.pk}"])

        # 90 000 + 100 000 + 9 000 = 199 000
        assert result.total_rub == 199_000
        assert result.variant == variant
        assert [o.option.name for o in result.options] == ["ABS"]
        assert result.on_request is False

    def test_included_options_ignored_in_sum_and_selection(self):
        moto = make_full_motorcycle()
        variant = moto.variants.first()

        result = quote(moto, CTX, variant.id, [f"usb_{moto.pk}"])

        assert result.total_rub == 190_000
        assert result.options == ()

    def test_duplicate_codes_deduplicated(self):
        moto = make_full_motorcycle()
        code = f"abs_{moto.pk}"

        result = quote(moto, CTX, moto.variants.first().id, [code, code, code])

        assert result.total_rub == 199_000
        assert len(result.options) == 1

    def test_unknown_variant_raises(self):
        moto = make_full_motorcycle()
        other = make_full_motorcycle()

        with pytest.raises(QuoteError, match="вариант"):
            quote(moto, CTX, other.variants.first().id, [])

    def test_unknown_option_raises_with_codes(self):
        moto = make_full_motorcycle()
        foreign = make_option_def(code="turbo")

        with pytest.raises(QuoteError, match="turbo"):
            quote(moto, CTX, moto.variants.first().id, [foreign.code, "nonexistent"])

    def test_option_of_other_model_is_unknown(self):
        moto = make_full_motorcycle()
        other = make_full_motorcycle()

        with pytest.raises(QuoteError):
            quote(moto, CTX, moto.variants.first().id, [f"abs_{other.pk}"])

    def test_price_on_request_variant(self):
        moto = make_motorcycle()
        variant = make_variant(moto, price_usd=None)

        result = quote(moto, CTX, variant.id, [])

        assert result.total_rub is None
        assert result.on_request is True

    def test_quote_matches_offer_for_no_options(self):
        moto = make_full_motorcycle()
        offer = build_offer(moto, CTX)

        for v in offer.variants:
            assert quote(moto, CTX, v.id, []).total_rub == v.price_rub


class TestCurrentContext:
    def test_uses_site_settings_and_last_rate(self, clock):
        make_site_settings(markup_rub=50_000, rounding_step=500)
        make_rate("91.2500", effective_date=date(2026, 11, 6), source="cbr_json")

        ctx = current_context()

        assert ctx.rate == Decimal("91.2500")
        assert ctx.markup_rub == 50_000
        assert ctx.step == 500
        assert ctx.rate_date == date(2026, 11, 6)
        assert ctx.rate_source == "cbr_json"

    def test_manual_rate(self, clock):
        make_site_settings(rate_mode=SiteSettings.RateMode.MANUAL, manual_rate=Decimal("100"))
        assert current_context().rate_source == "manual"

    def test_fallback_when_no_rate(self, clock, settings):
        ctx = current_context()
        assert ctx.rate == settings.RATES["FALLBACK"]
        assert ctx.rate_date is None
        assert ctx.rate_source == "fallback"


class TestPublishedMotorcycles:
    def test_only_published(self):
        visible = make_motorcycle(is_published=True)
        make_motorcycle(is_published=False)

        assert list(published_motorcycles()) == [visible]


class TestSiteSettings:
    def test_singleton_pk_is_always_one(self):
        first = SiteSettings.load()
        other = SiteSettings(markup_rub=1)
        other.save()

        assert first.pk == 1 and other.pk == 1
        assert SiteSettings.objects.count() == 1
        assert SiteSettings.load().markup_rub == 1

    def test_phone_raw(self):
        site = SiteSettings(phone="+7 (900) 123-45-67")
        assert site.phone_raw == "+79001234567"
        assert SiteSettings(phone="звоните").phone_raw == ""
