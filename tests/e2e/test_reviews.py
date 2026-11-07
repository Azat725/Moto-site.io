"""Отзывы: отправка формы, публикация только после одобрения модератором."""
from __future__ import annotations

import pytest
from playwright.sync_api import expect

from tests.e2e.helpers import dismiss_cookies, goto

pytestmark = pytest.mark.e2e

REVIEW_TEXT = "Отличный электромотоцикл, тихий и быстрый, менеджер помог с комплектацией."
SUCCESS_TEXT = "Спасибо! Отзыв появится на сайте после проверки."


def test_review_published_only_after_approval(page):
    from apps.reviews.models import Review

    goto(page, "/reviews/")
    dismiss_cookies(page)
    form = page.locator("form[data-review-form]")
    form.locator("#r-name").fill("Марат")
    form.locator("#r-city").fill("Нижнекамск")
    form.locator("#r-rating").select_option("5")
    form.locator("#r-model").select_option("hy-m")
    form.locator("#r-text").fill(REVIEW_TEXT)
    form.locator('input[name="consent"]').check()
    form.locator('input[name="publication_consent"]').check()
    with page.expect_response(lambda r: r.url.endswith("/reviews/submit/") and r.request.method == "POST") as info:
        form.locator('button[type="submit"]').click()
    assert info.value.status == 201, info.value.text()
    expect(form.locator('.form-status[role="status"]')).to_have_text(SUCCESS_TEXT)

    review = Review.objects.get()
    assert review.status == Review.Status.PENDING
    assert review.motorcycle.slug == "hy-m"

    goto(page, "/reviews/")
    expect(page.get_by_text(REVIEW_TEXT)).to_have_count(0)
    expect(page.locator(".review-card")).to_have_count(0)

    Review.objects.filter(pk=review.pk).update(status=Review.Status.APPROVED)
    goto(page, "/reviews/")
    card = page.locator(".review-card").filter(has_text=REVIEW_TEXT)
    expect(card).to_have_count(1)
    expect(card.locator("figcaption")).to_contain_text("Марат, Нижнекамск · HY-M")
    goto(page, "/moto/hy-m/")
    expect(page.locator(".review-card").filter(has_text=REVIEW_TEXT)).to_have_count(1)


def test_review_requires_both_consents(page):
    from apps.reviews.models import Review

    goto(page, "/reviews/")
    dismiss_cookies(page)
    form = page.locator("form[data-review-form]")
    form.locator("#r-name").fill("Марат")
    form.locator("#r-text").fill(REVIEW_TEXT)
    form.locator('input[name="consent"]').check()
    form.locator('button[type="submit"]').click()
    expect(form.locator(".check.is-invalid")).to_have_count(1)
    page.wait_for_timeout(300)
    assert Review.objects.count() == 0
