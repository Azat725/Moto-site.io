"""Общие шаги и расчёты для E2E-тестов."""
from __future__ import annotations

import json
import re
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

from playwright.sync_api import Page, expect

NBSP = chr(0xA0)
VECTORS_PATH = Path(__file__).resolve().parent.parent / "pricing_vectors.json"
DARK_BG = "rgb(11, 11, 12)"
COOKIE_VISIBLE = re.compile("(^| )is-visible( |$)")


def vector(name: str) -> dict:
    data = json.loads(VECTORS_PATH.read_text(encoding="utf-8"))
    return next(v for v in data["vectors"] if v["name"] == name)


def _kopecks(usd: str, rate: str) -> int:
    return int((Decimal(usd) * Decimal(rate) * 100).quantize(Decimal(1), rounding=ROUND_HALF_UP))


def expected_rub(rate: str, markup: int, step: int, variant_usd: str, options_usd=()) -> int:
    """Та же формула, что в pricing_vectors.json: компоненты в копейках, наценка, округление вверх до шага."""
    total = _kopecks(variant_usd, rate) + markup * 100 + sum(_kopecks(o, rate) for o in options_usd)
    unit = step * 100
    return -(-total // unit) * step


def expected_from_vector(name: str) -> int:
    v = vector(name)
    value = expected_rub(v["rate"], v["markup"], v["step"], v["variant_usd"], v["options_usd"])
    assert value == v["expected_rub"], f"формула теста расходится с вектором {name}"
    return value


def rub_text(value: int) -> str:
    """286000 → '286 000 ₽' с неразрывными пробелами, как в шаблоне и configurator.js."""
    return f"{value:,}".replace(",", NBSP) + NBSP + "₽"


def dismiss_cookies(page: Page) -> None:
    button = page.locator("[data-cookie-necessary]")
    expect(button).to_be_visible()
    button.click()
    expect(page.locator("#cookie")).not_to_have_class(COOKIE_VISIBLE)
    expect(button).to_be_hidden()


def choose_variant(page: Page, battery: str):
    """Клик по карточке варианта (как пользователь: input прозрачный и перекрыт телом карточки)."""
    label = page.locator("label.cfg-option--variant").filter(has_text=f"{battery} А·ч")
    expect(label).to_have_count(1)
    label.click()
    radio = label.locator('input[name="cfg-variant"]')
    expect(radio).to_be_checked()
    return radio


def set_option(page: Page, code: str, on: bool = True):
    label = page.locator(f'label.cfg-option:has(input[name="cfg-option"][value="{code}"])')
    box = label.locator("input")
    if box.is_checked() != on:
        label.click()
    if on:
        expect(box).to_be_checked()
    else:
        expect(box).not_to_be_checked()
    return box


def has_no_horizontal_scroll(page: Page) -> tuple[bool, dict]:
    sizes = page.evaluate(
        "() => ({scroll: document.documentElement.scrollWidth, client: document.documentElement.clientWidth})"
    )
    return sizes["scroll"] <= sizes["client"], sizes


def body_background(page: Page) -> str:
    return page.evaluate("() => getComputedStyle(document.body).backgroundColor")


def goto(page: Page, path: str) -> None:
    response = page.goto(path)
    assert response is not None and response.ok, f"{path}: HTTP {response.status if response else '—'}"
    assert body_background(page) == DARK_BG, "CSS не загрузился (фон body не тёмный)"
