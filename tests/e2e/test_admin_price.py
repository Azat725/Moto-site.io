"""Админка: вход, правка цены варианта HY-M через инлайн — новая цена сразу видна на публичной странице."""
from __future__ import annotations

import re

import pytest
from playwright.sync_api import expect

from tests.e2e.conftest import TEST_RATE
from tests.e2e.helpers import expected_rub, goto, rub_text

pytestmark = pytest.mark.e2e

USERNAME = "boss"
PASSWORD = "very-secret-password-123"  # совпадает с фикстурой superuser из tests/conftest.py


def login(page, admin_prefix: str) -> None:
    page.goto(admin_prefix)
    expect(page).to_have_url(re.compile(re.escape(admin_prefix) + r"login/"))
    page.locator("#id_username").fill(USERNAME)
    page.locator("#id_password").fill(PASSWORD)
    page.locator('#login-form [type="submit"]').click()
    expect(page.locator("#user-tools")).to_be_visible()


def test_admin_variant_price_change_updates_public_page(page, superuser, admin_prefix):
    from apps.catalog.models import Motorcycle

    new_price = expected_rub(str(TEST_RATE), 100_000, 1000, "3000")
    assert new_price == 344_000

    login(page, admin_prefix)
    page.goto(f"{admin_prefix}catalog/motorcycle/")
    expect(page.locator("#result_list")).to_be_visible()
    page.locator("#result_list").get_by_role("link", name="HY-M", exact=True).click()
    expect(page.locator("#motorcycle_form")).to_be_visible()

    first_price = page.locator('input[name="variants-0-price_usd"]')
    expect(first_price).to_have_value(re.compile(r"^2285(\.0+)?$"))
    first_price.fill("3000")
    page.locator('#motorcycle_form input[name="_save"]').click()
    expect(page.locator(".messagelist .success")).to_be_visible()
    expect(page.locator(".errornote")).to_have_count(0)

    moto = Motorcycle.objects.get(slug="hy-m")
    assert str(moto.variants.first().price_usd).rstrip("0").rstrip(".") == "3000"

    goto(page, "/moto/hy-m/")
    expect(page.locator("#cfg-total")).to_have_text(rub_text(new_price))
    expect(page.locator("label.cfg-option--variant").first.locator(".cfg-option__price")).to_have_text(
        rub_text(new_price))
