"""Страница модели: итог конфигуратора совпадает с эталонными векторами, скрытые поля заявки заполнены."""
from __future__ import annotations

import pytest
from playwright.sync_api import expect

from tests.e2e.conftest import TEST_RATE
from tests.e2e.helpers import (
    choose_variant,
    dismiss_cookies,
    expected_from_vector,
    expected_rub,
    goto,
    rub_text,
    set_option,
)

pytestmark = pytest.mark.e2e

JY_M_INCLUDED = {"camera", "waterproof_controls", "tft_tpms"}


def lead_hidden(page, name: str) -> str:
    return page.locator(f'#lead-model input[type="hidden"][name="{name}"]').input_value()


def variant_radio(page, battery: str):
    label = page.locator("label.cfg-option--variant").filter(has_text=f"{battery} А·ч")
    expect(label).to_have_count(1)
    return label.locator('input[name="cfg-variant"]')


def test_default_variant_total_matches_vector(page):
    expected = expected_from_vector("HY-M 60 А·ч без опций")
    goto(page, "/moto/hy-m/")
    total = page.locator("#cfg-total")
    expect(total).to_have_text(rub_text(expected))
    assert expected == 286_000
    expect(variant_radio(page, "60")).to_be_checked()
    expect(page.locator("label.cfg-option--variant").first.locator(".cfg-option__price")).to_have_text(rub_text(expected))
    assert lead_hidden(page, "client_total") == str(expected)


def test_options_on_120ah_match_vector_and_fill_hidden_fields(page):
    expected = expected_from_vector("HY-M 120 А·ч + ABS + TFT")
    goto(page, "/moto/hy-m/")
    dismiss_cookies(page)
    radio = choose_variant(page, "120")
    set_option(page, "abs")
    set_option(page, "tft_tpms")

    expect(page.locator("#cfg-total")).to_have_text(rub_text(expected))
    assert expected == 318_000
    expect(page.locator("#order-summary")).to_contain_text(rub_text(expected))

    color = page.locator('input[name="cfg-color"]:checked').get_attribute("value")
    assert lead_hidden(page, "variant") == radio.get_attribute("value")
    assert set(lead_hidden(page, "options").split(",")) == {"abs", "tft_tpms"}
    assert color and lead_hidden(page, "color") == color
    assert lead_hidden(page, "client_total") == str(expected)
    assert lead_hidden(page, "model") == "hy-m"


def test_unchecking_option_lowers_total(page):
    goto(page, "/moto/hy-m/")
    dismiss_cookies(page)
    set_option(page, "abs")
    with_abs = expected_rub(str(TEST_RATE), 100_000, 1000, "2285", ["223"])
    expect(page.locator("#cfg-total")).to_have_text(rub_text(with_abs))
    set_option(page, "abs", on=False)
    expect(page.locator("#cfg-total")).to_have_text(rub_text(expected_from_vector("HY-M 60 А·ч без опций")))
    assert lead_hidden(page, "options") == ""


def test_included_options_are_checked_and_disabled(page):
    goto(page, "/moto/jy-m/")
    included = page.locator(".cfg-option.is-included input")
    values = set(included.evaluate_all("els => els.map(e => e.value)"))
    assert values == JY_M_INCLUDED
    for i in range(included.count()):
        expect(included.nth(i)).to_be_checked()
        expect(included.nth(i)).to_be_disabled()
        expect(included.nth(i).locator("xpath=..").locator(".cfg-option__price")).to_have_text("в комплектации")
    # включённые опции не прибавляются к цене и не уходят в заявку как «выбранные»
    expect(page.locator("#cfg-total")).to_have_text(rub_text(expected_rub(str(TEST_RATE), 100_000, 1000, "2695")))
    assert lead_hidden(page, "options") == ""
