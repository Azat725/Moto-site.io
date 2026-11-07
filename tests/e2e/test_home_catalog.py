"""Главная — сначала каталог: карточки в первом экране, фильтры, адрес страницы, отсутствие горизонтальной прокрутки."""
from __future__ import annotations

import re

import pytest
from playwright.sync_api import expect

from tests.e2e.helpers import dismiss_cookies, goto, has_no_horizontal_scroll

pytestmark = pytest.mark.e2e

TOTAL_MODELS = 15
NAKED_SLUGS = {"dmg-m", "z1000-z"}
POWER_15_SLUGS = {"df-mx", "yl-mx", "hy-mx", "mc-mx"}


def visible_slugs(page) -> set[str]:
    hrefs = page.locator(".bike-item:not([hidden]) .bike-card__title a").evaluate_all(
        "els => els.map(a => a.getAttribute('href'))"
    )
    return {href.strip("/").split("/")[-1] for href in hrefs}


@pytest.mark.parametrize("width,height", [(1280, 800), (375, 812)])
def test_first_card_is_in_first_viewport(new_page, width, height):
    page, _ = new_page(width=width, height=height)
    goto(page, "/")
    dismiss_cookies(page)
    cards = page.locator(".bike-item")
    expect(cards).to_have_count(TOTAL_MODELS)
    top = page.evaluate("() => document.querySelector('.bike-item').getBoundingClientRect().top")
    assert 0 <= top < height, f"первая карточка начинается на {top}px при высоте экрана {height}px"


def test_type_and_power_filters_update_url_and_reset(page):
    goto(page, "/")
    dismiss_cookies(page)
    items = page.locator(".bike-item:not([hidden])")
    expect(items).to_have_count(TOTAL_MODELS)

    naked = page.locator('[data-filter="type"][data-value="naked"]')
    expect(naked).to_have_text("Нейкед")
    naked.click()
    expect(items).to_have_count(len(NAKED_SLUGS))
    expect(naked).to_have_attribute("aria-pressed", "true")
    assert visible_slugs(page) == NAKED_SLUGS
    assert page.locator(".bike-item:not([hidden])").evaluate_all("els => els.map(e => e.dataset.type)") == ["naked"] * 2
    expect(page).to_have_url(re.compile(r"/\?type=naked$"))

    page.locator('[data-filter="type"][data-value="all"]').click()
    power = page.locator('[data-filter="power"][data-value="15"]')
    expect(power).to_have_text("15 кВт")
    power.click()
    expect(items).to_have_count(len(POWER_15_SLUGS))
    assert visible_slugs(page) == POWER_15_SLUGS
    expect(page).to_have_url(re.compile(r"/\?power=15$"))

    page.locator("#f-reset").click()
    expect(items).to_have_count(TOTAL_MODELS)
    expect(page).to_have_url(re.compile(r"/$"))
    expect(page.locator("#catalog-count")).to_contain_text(str(TOTAL_MODELS))


def test_filters_restored_from_query_string(page):
    goto(page, "/?type=naked")
    expect(page.locator(".bike-item:not([hidden])")).to_have_count(len(NAKED_SLUGS))


SCROLL_THROUGH = """async () => {
  for (let y = 0; y < document.body.scrollHeight; y += 300) { window.scrollTo(0, y); await new Promise(r => setTimeout(r, 50)); }
  window.scrollTo(0, 0);
}"""


def scroll_cases():
    for path in ["/", "/catalog/", "/moto/hy-m/", "/reviews/"]:
        for width in [375, 768, 1280]:
            yield pytest.param(path, width, id=f"{path}-{width}")


@pytest.mark.parametrize("path,width", list(scroll_cases()))
def test_no_horizontal_scroll(new_page, width, path):
    page, _ = new_page(width=width, height=800)
    goto(page, path)
    page.wait_for_load_state("load")
    page.wait_for_timeout(800)  # анимации появления первого экрана
    problems = []
    ok, sizes = has_no_horizontal_scroll(page)
    if not ok:
        problems.append(f"после загрузки: scrollWidth {sizes['scroll']} > clientWidth {sizes['client']}")
    page.evaluate(SCROLL_THROUGH)
    page.wait_for_timeout(1200)
    ok, sizes = has_no_horizontal_scroll(page)
    if not ok:
        problems.append(f"после прокрутки: scrollWidth {sizes['scroll']} > clientWidth {sizes['client']}")
    assert not problems, f"{path} @ {width}px: " + "; ".join(problems)
