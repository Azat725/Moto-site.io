"""Заявка со страницы модели: успешная отправка, пересчёт цены на сервере, очередь уведомлений, согласие на ПДн."""
from __future__ import annotations

import re

import pytest
from playwright.sync_api import expect

from tests.e2e.helpers import choose_variant, dismiss_cookies, expected_from_vector, goto, set_option

pytestmark = pytest.mark.e2e

PHONE_DIGITS = "9171234567"
SUCCESS_TEXT = "Спасибо! Заявка принята — менеджер свяжется с вами в рабочее время."
CONSENT_ERROR = "Без согласия на обработку персональных данных мы не можем принять заявку."


def open_configured_model(page) -> None:
    goto(page, "/moto/hy-m/")
    dismiss_cookies(page)
    choose_variant(page, "120")
    set_option(page, "abs")
    set_option(page, "tft_tpms")


def fill_contacts(form, consent: bool) -> None:
    form.locator('input[name="name"]').fill("Иван Петров")
    form.locator('input[name="phone"]').fill(PHONE_DIGITS)
    expect(form.locator('input[name="phone"]')).to_have_value("+7 (917) 123-45-67")
    if consent:
        form.locator('input[name="consent"]').check()


def test_lead_is_saved_with_server_price_and_queued(page):
    from apps.leads.models import Lead, Outbox

    expected = expected_from_vector("HY-M 120 А·ч + ABS + TFT")
    open_configured_model(page)
    form = page.locator("#lead-model")
    fill_contacts(form, consent=True)
    with page.expect_response(lambda r: r.url.endswith("/api/leads/") and r.request.method == "POST") as resp_info:
        form.locator('button[type="submit"]').click()
    response = resp_info.value
    assert response.status == 201, response.text()
    status = form.locator(".form-status")
    expect(status).to_have_text(SUCCESS_TEXT)
    expect(status).to_have_class(re.compile(r"is-ok"))

    lead = Lead.objects.get()
    assert lead.kind == Lead.Kind.MODEL
    assert lead.model_name == "HY-M"
    assert lead.total_rub == expected
    assert lead.config["variant"] == "72 В · 120 А·ч"
    assert lead.config["client_total"] == expected
    assert lead.config["options"] == ["ABS", "Цветной TFT-дисплей + датчики давления в шинах"]
    assert lead.config["color"] == "Чёрный"
    assert lead.phone == "+7" + PHONE_DIGITS
    assert lead.consent_at is not None
    assert lead.page == "/moto/hy-m/"

    channels = {row.channel: row for row in Outbox.objects.filter(lead=lead)}
    assert set(channels) == {Outbox.Channel.EMAIL, Outbox.Channel.TELEGRAM}
    assert channels[Outbox.Channel.EMAIL].status == Outbox.Status.PENDING
    telegram_digits = re.sub(r"\D", "", channels[Outbox.Channel.TELEGRAM].body)
    assert PHONE_DIGITS not in telegram_digits, "телефон (ПДн) попал в Telegram при INCLUDE_PD=False"
    assert "Иван" not in channels[Outbox.Channel.TELEGRAM].body


def submit_without_consent(page):
    goto(page, "/moto/hy-m/")
    dismiss_cookies(page)
    posts = []
    page.on("request", lambda r: posts.append(r.url) if "/api/leads/" in r.url else None)
    form = page.locator("#lead-model")
    fill_contacts(form, consent=False)
    form.locator('button[type="submit"]').click()
    return form, posts


def test_submit_without_consent_is_blocked(page):
    from apps.leads.models import Lead

    form, posts = submit_without_consent(page)
    expect(form.locator(".check")).to_have_class(re.compile(r"is-invalid"))
    expect(form.locator("[data-consent-error]")).not_to_have_attribute("hidden", "")
    expect(form.locator("[data-consent-error]")).to_have_text(CONSENT_ERROR)
    page.wait_for_timeout(500)
    assert posts == []
    assert Lead.objects.count() == 0
    expect(form.locator(".form-status")).to_have_text("")


def test_consent_error_message_is_visible(page):
    form, _ = submit_without_consent(page)
    expect(form.locator("[data-consent-error]")).to_be_visible(timeout=2000)


def test_empty_submit_marks_required_fields(page):
    from apps.leads.models import Lead

    goto(page, "/moto/hy-m/")
    dismiss_cookies(page)
    form = page.locator("#lead-model")
    form.locator('button[type="submit"]').click()
    expect(form.locator(".field.is-invalid")).to_have_count(2)
    expect(form.locator(".field.is-invalid .field__error").first).to_be_visible()
    expect(form.locator(".check.is-invalid")).to_have_count(1)
    expect(form.locator('input[name="name"]')).to_be_focused()
    page.wait_for_timeout(300)
    assert Lead.objects.count() == 0
