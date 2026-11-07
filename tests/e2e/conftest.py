"""Фикстуры Playwright E2E: системный Google Chrome, живой сервер Django, засеянный каталог.

Тесты запускаются только при RUN_E2E=1 (иначе помечаются как skipped), чтобы обычный `pytest` оставался быстрым:
    RUN_E2E=1 .venv/Scripts/python -m pytest -m e2e tests/e2e -q
"""
from __future__ import annotations

import os
from collections.abc import Iterator
from decimal import Decimal
from pathlib import Path

import pytest

E2E_DIR = Path(__file__).resolve().parent
RUN_E2E = os.environ.get("RUN_E2E") == "1"
TEST_RATE = Decimal("81.1234")
HEADLESS = os.environ.get("E2E_HEADED") != "1"

if RUN_E2E:
    # Sync API Playwright держит event loop в главном потоке — без этого ORM в тесте падает с SynchronousOnlyOperation.
    os.environ.setdefault("DJANGO_ALLOW_ASYNC_UNSAFE", "true")


def pytest_collection_modifyitems(config, items):
    if RUN_E2E:
        return
    skip = pytest.mark.skip(reason="E2E-тесты Playwright: запуск с RUN_E2E=1")
    for item in items:
        if E2E_DIR in Path(str(item.fspath)).resolve().parents:
            item.add_marker(skip)


@pytest.fixture(scope="session")
def browser():
    from playwright.sync_api import sync_playwright

    with sync_playwright() as pw:
        chrome = pw.chromium.launch(channel="chrome", headless=HEADLESS)
        yield chrome
        chrome.close()


@pytest.fixture
def site(transactional_db, live_server, settings):
    """Живой сервер с каталогом из seed и курсом 81.1234 на сегодня. Возвращает базовый URL."""
    from django.utils import timezone

    from apps.catalog.seed_loader import seed_catalog
    from apps.rates.models import Rate

    settings.SITE_MODE = "live"
    settings.SHOW_SAMPLE_REVIEWS = False
    seed_catalog(with_photos=False)
    Rate.objects.create(currency="USD", value=TEST_RATE, effective_date=timezone.localdate(), source="test")
    return live_server.url


class ConsoleLog:
    """Ошибки консоли и необработанные исключения страницы."""

    def __init__(self) -> None:
        self.errors: list[str] = []

    def attach(self, page) -> None:
        page.on("console", lambda msg: self.errors.append(f"console.{msg.type}: {msg.text} @ {page.url}")
                if msg.type == "error" else None)
        page.on("pageerror", lambda exc: self.errors.append(f"pageerror: {exc} @ {page.url}"))


@pytest.fixture
def new_page(browser, site) -> Iterator:
    """Фабрика страниц: new_page(width=..., height=..., reduced_motion=...) → (page, console)."""
    contexts = []

    def factory(width: int = 1280, height: int = 800, reduced_motion: str = "no-preference", skip_preloader=True):
        context = browser.new_context(base_url=site, viewport={"width": width, "height": height},
                                      reduced_motion=reduced_motion, locale="ru-RU")
        context.set_default_timeout(10_000)
        if skip_preloader:
            context.add_init_script("try { sessionStorage.setItem('ivax_seen', '1'); } catch (e) {}")
        contexts.append(context)
        page = context.new_page()
        console = ConsoleLog()
        console.attach(page)
        return page, console

    yield factory
    for context in contexts:
        context.close()


@pytest.fixture
def page(new_page):
    pg, _ = new_page()
    return pg
