"""Ценообразование: чистые функции без БД."""
import json
from decimal import Decimal
from pathlib import Path

import pytest

from apps.catalog import pricing

VECTORS = json.loads((Path(__file__).resolve().parents[1] / "pricing_vectors.json").read_text(encoding="utf-8"))["vectors"]


@pytest.mark.parametrize("vector", VECTORS, ids=[v["name"] for v in VECTORS])
def test_vectors(vector):
    ctx = pricing.PriceContext(rate=Decimal(vector["rate"]), markup_rub=vector["markup"], step=vector["step"])
    variant = pricing.variant_kopecks(Decimal(vector["variant_usd"]), ctx)
    options = [pricing.option_kopecks(Decimal(o), ctx) for o in vector["options_usd"]]
    assert pricing.total_rub(variant, options, ctx.step) == vector["expected_rub"]


def test_to_kopecks_rounds_half_up():
    assert pricing.to_kopecks(Decimal("0.005"), Decimal("1")) == 1
    assert pricing.to_kopecks(Decimal("0.004"), Decimal("1")) == 0


def test_ceil_to_step_exact_and_above():
    assert pricing.ceil_to_step(100_000_00, 1000) == 100_000
    assert pricing.ceil_to_step(100_000_01, 1000) == 101_000
    assert pricing.ceil_to_step(1, 1) == 1


def test_ceil_to_step_rejects_bad_step():
    with pytest.raises(ValueError):
        pricing.ceil_to_step(100, 0)


def test_price_on_request_returns_none():
    ctx = pricing.PriceContext(rate=Decimal("90"), markup_rub=100000, step=1000)
    assert pricing.variant_kopecks(None, ctx) is None
    assert pricing.total_rub(None, [100], 1000) is None


def test_option_without_price_is_free():
    ctx = pricing.PriceContext(rate=Decimal("90"), markup_rub=100000, step=1000)
    assert pricing.option_kopecks(None, ctx) == 0


def test_context_validation():
    with pytest.raises(ValueError):
        pricing.PriceContext(rate=Decimal("0"), markup_rub=0, step=1000)
    with pytest.raises(ValueError):
        pricing.PriceContext(rate=Decimal("80"), markup_rub=-1, step=1000)


def test_display_rub_rounds_up_to_rubles():
    assert pricing.display_rub(1_000_01) == 1001
    assert pricing.display_rub(1_000_00) == 1000


def test_inputs_are_not_mutated():
    ctx = pricing.PriceContext(rate=Decimal("80"), markup_rub=1000, step=1000)
    options = (100, 200)
    pricing.total_rub(5000, options, ctx.step)
    assert options == (100, 200)
