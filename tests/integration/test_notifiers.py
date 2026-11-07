"""Доставка уведомлений из очереди: Telegram (responses), e-mail (locmem), повторы и отказ."""
from datetime import timedelta

import pytest
import requests
from django.core import mail
from django.core.management import call_command

from apps.leads import notifiers
from apps.leads.models import Lead, Outbox
from apps.leads.notifiers import deliver, email_subject, email_text, process_due, telegram_enabled, telegram_text
from tests.factories import make_lead, make_outbox

pytestmark = pytest.mark.django_db

TG_URL = "https://tg.test/bot123:test/sendMessage"


class TestDeliverTelegram:
    def test_success_marks_sent(self, rsps, clock):
        rsps.post(TG_URL, json={"ok": True}, status=200)
        item = make_outbox(body="<b>hi</b>", last_error="old")

        assert deliver(item) is True

        item.refresh_from_db()
        assert item.status == Outbox.Status.SENT
        assert item.attempts == 1
        assert item.sent_at == clock.current
        assert item.last_error == ""
        sent = rsps.calls[0].request
        import json

        assert json.loads(sent.body) == {"chat_id": "42", "text": "<b>hi</b>", "parse_mode": "HTML",
                                         "disable_web_page_preview": True}

    def test_http_error_increments_attempts_and_schedules_backoff(self, rsps, clock, settings):
        rsps.post(TG_URL, status=502)
        item = make_outbox()

        assert deliver(item) is False

        item.refresh_from_db()
        assert item.status == Outbox.Status.PENDING
        assert item.attempts == 1
        assert item.last_error == "RuntimeError: Telegram ответил 502"
        assert item.next_attempt_at == clock.current + timedelta(seconds=settings.OUTBOX_BACKOFF_SECONDS[0])

    def test_network_error_is_caught(self, rsps, clock):
        rsps.post(TG_URL, body=requests.ConnectionError("no route"))
        item = make_outbox()

        assert deliver(item) is False
        item.refresh_from_db()
        assert item.last_error.startswith("ConnectionError")

    @pytest.mark.parametrize("attempts_before, expected_delay", [(1, 300), (5, 43200), (6, 86400)])
    def test_backoff_grows_and_caps(self, rsps, clock, attempts_before, expected_delay):
        rsps.post(TG_URL, status=500)
        item = make_outbox(attempts=attempts_before)

        deliver(item)

        item.refresh_from_db()
        assert item.next_attempt_at == clock.current + timedelta(seconds=expected_delay)

    def test_backoff_uses_last_step_when_schedule_shorter(self, rsps, clock, settings):
        settings.OUTBOX_BACKOFF_SECONDS = [10, 20]
        settings.OUTBOX_MAX_ATTEMPTS = 100
        rsps.post(TG_URL, status=500)
        item = make_outbox(attempts=10)

        deliver(item)

        item.refresh_from_db()
        assert item.next_attempt_at == clock.current + timedelta(seconds=20)

    def test_dead_after_max_attempts(self, rsps, clock, settings):
        rsps.post(TG_URL, status=500)
        item = make_outbox(attempts=settings.OUTBOX_MAX_ATTEMPTS - 1)

        assert deliver(item) is False

        item.refresh_from_db()
        assert item.status == Outbox.Status.DEAD
        assert item.attempts == settings.OUTBOX_MAX_ATTEMPTS

    def test_long_error_truncated(self, monkeypatch, clock):
        def fail(item):
            raise RuntimeError("x" * 1000)

        monkeypatch.setitem(notifiers.SENDERS, Outbox.Channel.TELEGRAM, fail)
        item = make_outbox()

        deliver(item)

        item.refresh_from_db()
        assert len(item.last_error) == 500


class TestDeliverEmail:
    def test_email_sent_via_locmem(self, clock):
        item = make_outbox(channel=Outbox.Channel.EMAIL, subject="Заявка №1", body="Имя: Иван")

        assert deliver(item) is True

        assert len(mail.outbox) == 1
        assert mail.outbox[0].subject == "Заявка №1"
        assert mail.outbox[0].to == ["manager@example.com"]
        assert mail.outbox[0].body == "Имя: Иван"
        item.refresh_from_db()
        assert item.status == Outbox.Status.SENT

    def test_no_recipients_is_a_failure(self, clock, settings):
        settings.LEAD_NOTIFY_EMAILS = []
        item = make_outbox(channel=Outbox.Channel.EMAIL)

        assert deliver(item) is False
        item.refresh_from_db()
        assert "LEAD_NOTIFY_EMAILS" in item.last_error
        assert len(mail.outbox) == 0


class TestProcessDue:
    def test_only_due_pending_items_processed(self, rsps, clock):
        rsps.post(TG_URL, status=200)
        due = make_outbox(next_attempt_at=clock.current - timedelta(minutes=1))
        future = make_outbox(next_attempt_at=clock.current + timedelta(minutes=1))
        sent = make_outbox(status=Outbox.Status.SENT, next_attempt_at=clock.current - timedelta(hours=1))
        dead = make_outbox(status=Outbox.Status.DEAD, next_attempt_at=clock.current - timedelta(hours=1))

        assert process_due() == (1, 0)

        due.refresh_from_db()
        future.refresh_from_db()
        assert due.status == Outbox.Status.SENT
        assert future.status == Outbox.Status.PENDING
        assert len(rsps.calls) == 1
        assert {sent.pk, dead.pk}.isdisjoint({due.pk, future.pk})

    def test_counts_failures_and_respects_limit(self, rsps, clock):
        rsps.post(TG_URL, status=500)
        for _ in range(3):
            make_outbox(next_attempt_at=clock.current)

        assert process_due(limit=2) == (0, 2)
        assert Outbox.objects.filter(attempts=0).count() == 1

    def test_send_notifications_command(self, rsps, clock, capsys):
        rsps.post(TG_URL, status=200)
        make_outbox(next_attempt_at=clock.current)
        make_outbox(channel=Outbox.Channel.EMAIL, next_attempt_at=clock.current)

        call_command("send_notifications")

        assert "Отправлено: 2, с ошибкой (будет повтор): 0" in capsys.readouterr().out


class TestTexts:
    def test_telegram_enabled_requires_token_and_chat(self, settings):
        assert telegram_enabled() is True
        settings.TELEGRAM = {**settings.TELEGRAM, "CHAT_ID": ""}
        assert telegram_enabled() is False

    def test_telegram_text_callback_has_admin_link(self, settings):
        lead = make_lead(kind=Lead.Kind.CALLBACK)

        text = telegram_text(lead)

        assert f'{settings.SITE_DOMAIN}/{settings.ADMIN_PATH}leads/lead/{lead.pk}/change/' in text
        assert "Обратный звонок" in text
        assert "Итого" not in text

    def test_rate_note_and_price_on_request(self):
        lead = make_lead(model_name="Storm", total_rub=None,
                         config={"variant": "V", "options": ["ABS"], "color": "Red", "rate": "90", "rate_date": "d"})

        text = telegram_text(lead)

        assert "Итого: по запросу (курс 90 на d)" in text
        assert "Опции: ABS" in text and "Цвет: Red" in text and "Комплектация: V" in text

    def test_total_formatted_with_spaces(self):
        lead = make_lead(model_name="Storm", total_rub=1_234_000, config={})
        assert "Итого: 1 234 000 ₽" in telegram_text(lead)

    def test_email_text_contains_contacts_and_message(self, clock):
        lead = make_lead(message="Позвоните после 18:00", page="")

        text = email_text(lead)

        assert "Имя: Иван" in text and "Телефон: +79123456789" in text
        assert "Комментарий: Позвоните после 18:00" in text
        assert "Страница: —" in text
        assert "07.11.2026 12:00" in text, "время в часовом поясе Москвы"

    def test_email_subject_strips_newlines(self):
        lead = make_lead(model_name="Bike\r\nBcc: x@evil")
        assert "\n" not in email_subject(lead) and "\r" not in email_subject(lead)
