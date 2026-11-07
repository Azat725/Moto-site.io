"""Консоль без ошибок на ключевых страницах; при prefers-reduced-motion контент с [data-reveal] сразу виден."""
from __future__ import annotations

import pytest

from tests.e2e.helpers import goto

pytestmark = pytest.mark.e2e

PAGES = ["/", "/catalog/", "/moto/jy-mx/", "/reviews/"]


@pytest.mark.parametrize("path", PAGES)
def test_no_console_errors(new_page, path):
    page, console = new_page()
    failed = []
    page.on("response", lambda r: failed.append(f"{r.status} {r.url}") if r.status >= 400 else None)
    goto(page, path)
    page.wait_for_load_state("load")
    page.mouse.wheel(0, 3000)
    page.wait_for_timeout(1000)
    assert console.errors == []
    assert failed == []


@pytest.mark.parametrize("path", PAGES)
def test_reduced_motion_reveals_content(new_page, path):
    page, console = new_page(reduced_motion="reduce", skip_preloader=False)
    goto(page, path)
    assert page.evaluate("() => document.documentElement.classList.contains('reduce')")
    states = page.locator("[data-reveal]").evaluate_all(
        "els => els.map(e => ({cls: e.className, opacity: getComputedStyle(e).opacity,"
        " transform: getComputedStyle(e).transform}))"
    )
    assert states, "на странице нет элементов [data-reveal]"
    hidden = [s for s in states if s["opacity"] != "1" or s["transform"] not in ("none", "")]
    assert hidden == []
    preloader_display = page.evaluate(
        "() => { const p = document.getElementById('preloader'); return p ? getComputedStyle(p).display : 'none'; }"
    )
    assert preloader_display == "none"
    assert console.errors == []
