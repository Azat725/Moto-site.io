"""Реальные сценарии сотрудника в Chrome: справочник, модерация и обезличивание."""
from pathlib import Path

import pytest
from playwright.sync_api import expect

from tests.e2e.helpers import has_no_horizontal_scroll
from tests.e2e.test_admin_price import login

pytestmark = pytest.mark.e2e
ARTIFACTS = Path(__file__).resolve().parents[2] / "test-results" / "admin"


def test_color_create_search_edit_delete(page, superuser, admin_prefix):
    from apps.catalog.models import Color

    login(page, admin_prefix)
    page.goto(f"{admin_prefix}catalog/color/add/")
    page.locator('[name="code"]').fill("qa_color")
    page.locator('[name="name"]').fill("Проверочный цвет")
    page.locator('[name="hex"]').fill("не цвет")
    page.locator('[name="sort_order"]').fill("10")
    page.locator('[name="_save"]').click()
    expect(page.locator(".errornote")).to_be_visible()
    assert not Color.objects.filter(code="qa_color").exists()
    page.locator('[name="hex"]').fill("#E10600")
    page.locator('[name="_save"]').click()
    expect(page.locator(".success")).to_be_visible()
    page.locator('[name="q"]').fill("qa_color")
    page.locator('#changelist-search [type="submit"]').click()
    expect(page.locator("#result_list tbody tr")).to_have_count(1)
    page.get_by_role("link", name="Проверочный цвет", exact=True).click()
    page.locator('[name="name"]').fill("Изменённый цвет")
    page.locator('[name="_save"]').click()
    assert Color.objects.get(code="qa_color").name == "Изменённый цвет"
    page.locator("#result_list").get_by_role("link", name="Изменённый цвет", exact=True).click()
    page.locator(".deletelink").click()
    expect(page.locator('[name="post"]')).to_have_value("yes")
    page.locator('#content [type="submit"]').click()
    assert not Color.objects.filter(code="qa_color").exists()


def test_moderate_review_and_filter(page, superuser, admin_prefix):
    from apps.reviews.models import Review
    from tests.factories import make_review

    review = make_review(status=Review.Status.PENDING)
    login(page, admin_prefix)
    page.goto(f"{admin_prefix}reviews/review/?status__exact=pending")
    expect(page.locator("#result_list tbody tr")).to_have_count(1)
    page.locator("#result_list tbody th a").click()
    expect(page.locator('[name="text"]')).to_have_count(0)
    page.locator('[name="status"]').select_option("approved")
    page.locator('[name="_save"]').click()
    review.refresh_from_db()
    assert review.status == Review.Status.APPROVED and review.moderated_at
    page.goto("/reviews/")
    expect(page.get_by_text(review.text, exact=False)).to_be_visible()


def test_anonymization_confirmation(page, superuser, admin_prefix):
    from tests.factories import make_lead

    lead = make_lead()
    login(page, admin_prefix)
    page.goto(f"{admin_prefix}leads/lead/")
    page.locator(f'[name="_selected_action"][value="{lead.pk}"]').check()
    page.locator('[name="action"]').first.select_option("anonymize")
    page.locator('[name="index"]').first.click()
    expect(page.get_by_role("heading", name="Подтвердить обезличивание")).to_be_visible()
    lead.refresh_from_db()
    assert lead.name == "Иван"
    page.get_by_role("button", name="Подтвердить обезличивание").click()
    lead.refresh_from_db()
    assert lead.name == "—" and lead.anonymized_at


@pytest.mark.parametrize("width", [375, 768, 1280])
def test_admin_responsive_console_and_network(new_page, superuser, admin_prefix, width):
    from apps.catalog.models import Motorcycle

    page, console = new_page(width=width, reduced_motion="reduce")
    failures = []
    page.on("response", lambda r: failures.append(f"{r.status} {r.url}") if r.status >= 400 else None)
    login(page, admin_prefix)
    moto = Motorcycle.objects.get(slug="hy-m")
    for label, tail in [("index", ""), ("catalog", "catalog/motorcycle/"),
                        ("model", f"catalog/motorcycle/{moto.pk}/change/"),
                        ("settings", "catalog/sitesettings/1/change/"), ("leads", "leads/lead/"),
                        ("reviews", "reviews/review/"), ("import", "catalog/motorcycle/import/"),
                        ("rates", "rates/rate/"), ("outbox", "leads/outbox/")]:
        page.goto(admin_prefix + tail)
        page.wait_for_load_state("networkidle")
        ok, sizes = has_no_horizontal_scroll(page)
        assert ok, (tail, width, sizes)
        ARTIFACTS.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(ARTIFACTS / f"{label}-{width}.png"), full_page=True)
    assert console.errors == [] and failures == []


def test_admin_and_catalog_work_without_javascript(browser, site, superuser, admin_prefix):
    context = browser.new_context(base_url=site, java_script_enabled=False)
    try:
        page = context.new_page()
        login(page, admin_prefix)
        expect(page.get_by_role("heading", name="Каталог, заявки и отзывы")).to_be_visible()
        page.goto("/moto/hy-m/")
        expect(page.get_by_role("heading", level=1)).to_contain_text("HY-M")
        expect(page.locator("#configurator")).to_be_visible()
    finally:
        context.close()
