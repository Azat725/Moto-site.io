"""Доставка уведомлений из очереди: захват записи, Telegram (responses), e-mail (locmem), повторы и отказ."""
import json
from datetime import timedelta

import pytest
import requests
from django.core import mail
from django.core.management import call_command

from apps.leads import delivery, notifiers
from apps.leads.delivery import LOCK_SECONDS, claim, deliver, due_ids, process_due
from apps.leads.models import Outbox
from tests.factories import make_outbox

pytestmark = pytest.mark.django_db

TG_URL = "https://tg.test/bot123:test/sendMessage"


def _due(clock, **kw):
    return make_outbox(next_attempt_at=clock.current - timedelta(seconds=1), **kw)


def _reload(item: Outbox) -> Outbox:
    return Outbox.objects.get(pk=item.pk)


class TestClaim:
    def test_due_pending_is_claimed_once(self, clock):
        item = _due(clock)

        until = claim(item.pk)
        assert until == clock.current + timedelta(seconds=LOCK_SECONDS)
        assert claim(item.pk) is None, "второй процесс не должен получить ту же запись"

        item = _reload(item)
        assert item.status == Outbox.Status.SENDING
        assert item.locked_until == until

    def test_pending_due_exactly_now_is_claimed(self, clock):
        assert claim(make_outbox(next_attempt_at=clock.current).pk) is not None

    def test_future_pending_not_claimed(self, clock):
        assert claim(make_outbox(next_attempt_at=clock.current + timedelta(seconds=1)).pk) is None

    def test_expired_sending_lock_is_reclaimable(self, clock):
        item = make_outbox(status=Outbox.Status.SENDING, next_attempt_at=clock.current,
                           locked_until=clock.current - timedelta(seconds=1))
        assert claim(item.pk) is not None

    def test_active_sending_lock_not_reclaimable(self, clock):
        item = make_outbox(status=Outbox.Status.SENDING, next_attempt_at=clock.current,
                           locked_until=clock.current + timedelta(seconds=30))
        assert claim(item.pk) is None

    @pytest.mark.parametrize("status", [Outbox.Status.SENT, Outbox.Status.DEAD])
    def test_finished_items_not_claimed(self, clock, status):
        assert claim(_due(clock, status=status).pk) is None

    def test_unknown_id(self):
        assert claim(999_999) is None


class TestDeliverTelegram:
    def test_success_marks_sent(self, rsps, clock):
        rsps.post(TG_URL, json={"ok": True}, status=200)
        item = _due(clock, body="<b>hi</b>", last_error="old")

        assert deliver(item.pk) is True

        item = _reload(item)
        assert item.status == Outbox.Status.SENT
        assert item.attempts == 1
        assert item.sent_at == clock.current
        assert item.last_error == "" and item.locked_until is None
        assert item.body == "<b>hi</b>", "текст Telegram (без ПДн) остаётся для истории"
        assert json.loads(rsps.calls[0].request.body) == {
            "chat_id": "42", "text": "<b>hi</b>", "parse_mode": "HTML", "disable_web_page_preview": True}

    def test_already_claimed_row_not_sent_twice(self, rsps, clock):
        rsps.post(TG_URL, status=200)
        item = _due(clock)
        assert claim(item.pk) is not None  # другой воркер уже взял запись

        assert deliver(item.pk) is False
        assert len(rsps.calls) == 0

    def test_second_deliver_after_success_is_noop(self, rsps, clock):
        rsps.post(TG_URL, status=200)
        item = _due(clock)

        assert deliver(item.pk) is True
        assert deliver(item.pk) is False
        assert len(rsps.calls) == 1

    def test_http_error_schedules_backoff(self, rsps, clock, settings):
        rsps.post(TG_URL, status=502)
        item = _due(clock)

        assert deliver(item.pk) is False

        item = _reload(item)
        assert item.status == Outbox.Status.PENDING
        assert item.attempts == 1
        assert item.last_error == "Telegram ответил 502"
        assert item.locked_until is None
        assert item.next_attempt_at == clock.current + timedelta(seconds=settings.OUTBOX_BACKOFF_SECONDS[0])

    def test_network_error_does_not_leak_bot_token(self, rsps, clock):
        rsps.post(TG_URL, body=requests.ConnectionError(f"Max retries exceeded with url: {TG_URL}"))
        item = _due(clock)

        assert deliver(item.pk) is False

        item = _reload(item)
        assert item.last_error == "Telegram недоступен: ConnectionError"
        assert "123:test" not in item.last_error and "bot" not in item.last_error

    def test_timeout_does_not_leak_bot_token(self, rsps, clock):
        rsps.post(TG_URL, body=requests.Timeout(TG_URL))
        item = _due(clock)

        deliver(item.pk)

        assert "123:test" not in _reload(item).last_error

    def test_send_telegram_raises_notify_error(self, rsps):
        rsps.post(TG_URL, status=403)
        with pytest.raises(notifiers.NotifyError, match="403"):
            notifiers.send_telegram(Outbox(body="x"))

    @pytest.mark.parametrize("attempts_before, expected_delay", [(0, 60), (1, 300), (5, 43200), (6, 86400)])
    def test_backoff_grows(self, rsps, clock, attempts_before, expected_delay):
        rsps.post(TG_URL, status=500)
        item = _due(clock, attempts=attempts_before)

        deliver(item.pk)

        assert _reload(item).next_attempt_at == clock.current + timedelta(seconds=expected_delay)

    def test_backoff_caps_at_last_step(self, rsps, clock, settings):
        settings.OUTBOX_BACKOFF_SECONDS = [10, 20]
        settings.OUTBOX_MAX_ATTEMPTS = 100
        rsps.post(TG_URL, status=500)
        item = _due(clock, attempts=10)

        deliver(item.pk)

        assert _reload(item).next_attempt_at == clock.current + timedelta(seconds=20)

    def test_dead_after_max_attempts(self, rsps, clock, settings):
        rsps.post(TG_URL, status=500)
        item = _due(clock, attempts=settings.OUTBOX_MAX_ATTEMPTS - 1)

        assert deliver(item.pk) is False

        item = _reload(item)
        assert item.status == Outbox.Status.DEAD
        assert item.attempts == settings.OUTBOX_MAX_ATTEMPTS
        assert claim(item.pk) is None

    def test_unexpected_exception_recorded_with_type(self, monkeypatch, clock):
        def fail(item):
            raise ValueError("x" * 1000)

        monkeypatch.setitem(delivery.SENDERS, Outbox.Channel.TELEGRAM, fail)
        item = _due(clock)

        assert deliver(item.pk) is False

        item = _reload(item)
        assert item.last_error.startswith("ValueError: xxx")
        assert len(item.last_error) == 500
        assert item.status == Outbox.Status.PENDING


class TestStaleWorker:
    def test_stale_worker_cannot_overwrite_new_owner(self, monkeypatch, clock):
        """Воркер A завис дольше LOCK_SECONDS, запись забрал B — итог A не должен затирать состояние B."""
        item = _due(clock)
        taken = {}

        def slow_send(outbox):
            clock.set(clock.current + timedelta(seconds=LOCK_SECONDS + 1))
            taken["until"] = claim(outbox.pk)  # воркер B

        monkeypatch.setitem(delivery.SENDERS, Outbox.Channel.TELEGRAM, slow_send)

        deliver(item.pk)

        item = _reload(item)
        assert taken["until"] is not None
        assert item.status == Outbox.Status.SENDING and item.locked_until == taken["until"]
        assert item.attempts == 0 and item.sent_at is None

    def test_stale_worker_failure_not_recorded(self, monkeypatch, clock):
        item = _due(clock)

        def slow_fail(outbox):
            clock.set(clock.current + timedelta(seconds=LOCK_SECONDS + 1))
            claim(outbox.pk)
            raise RuntimeError("boom")

        monkeypatch.setitem(delivery.SENDERS, Outbox.Channel.TELEGRAM, slow_fail)

        assert deliver(item.pk) is False
        item = _reload(item)
        assert item.attempts == 0 and item.last_error == "" and item.status == Outbox.Status.SENDING

    def test_row_deleted_after_claim(self, monkeypatch, rsps, clock):
        item = _due(clock)
        real_claim = delivery.claim

        def claim_then_delete(pk):
            until = real_claim(pk)
            Outbox.objects.filter(pk=pk).delete()
            return until

        monkeypatch.setattr(delivery, "claim", claim_then_delete)

        assert deliver(item.pk) is False
        assert len(rsps.calls) == 0


class TestDeliverEmail:
    def test_email_sent_via_locmem(self, clock):
        item = _due(clock, channel=Outbox.Channel.EMAIL, subject="Заявка №1", body="Имя: Иван")

        assert deliver(item.pk) is True

        assert len(mail.outbox) == 1
        assert mail.outbox[0].subject == "Заявка №1"
        assert mail.outbox[0].to == ["manager@example.com"]
        assert mail.outbox[0].body == "Имя: Иван"
        item = _reload(item)
        assert item.status == Outbox.Status.SENT
        assert item.body == "[отправлено, текст удалён]", "ПДн из письма не хранятся после отправки"

    def test_failed_email_keeps_body_for_retry(self, clock, settings):
        settings.LEAD_NOTIFY_EMAILS = []
        item = _due(clock, channel=Outbox.Channel.EMAIL, body="Имя: Иван")

        deliver(item.pk)

        assert _reload(item).body == "Имя: Иван"

    def test_no_recipients_is_a_failure(self, clock, settings):
        settings.LEAD_NOTIFY_EMAILS = []
        item = _due(clock, channel=Outbox.Channel.EMAIL)

        assert deliver(item.pk) is False
        assert _reload(item).last_error == "Не заданы LEAD_NOTIFY_EMAILS"
        assert len(mail.outbox) == 0


class TestProcessDue:
    def test_due_ids_selects_pending_due_and_expired_locks(self, clock):
        due = _due(clock)
        expired = make_outbox(status=Outbox.Status.SENDING, next_attempt_at=clock.current,
                              locked_until=clock.current - timedelta(seconds=1))
        make_outbox(next_attempt_at=clock.current + timedelta(minutes=1))
        make_outbox(status=Outbox.Status.SENDING, next_attempt_at=clock.current,
                    locked_until=clock.current + timedelta(minutes=1))
        _due(clock, status=Outbox.Status.SENT)
        _due(clock, status=Outbox.Status.DEAD)

        assert due_ids() == [due.pk, expired.pk]

    def test_due_ids_limit_and_order(self, clock):
        items = [_due(clock) for _ in range(3)]
        assert due_ids(limit=2) == [items[0].pk, items[1].pk]

    def test_process_due_counts(self, rsps, clock):
        rsps.post(TG_URL, status=200)
        _due(clock)
        _due(clock, channel=Outbox.Channel.EMAIL)
        future = make_outbox(next_attempt_at=clock.current + timedelta(minutes=1))

        assert process_due() == (2, 0)
        assert _reload(future).status == Outbox.Status.PENDING

    def test_process_due_failures_and_limit(self, rsps, clock):
        rsps.post(TG_URL, status=500)
        for _ in range(3):
            _due(clock)

        assert process_due(limit=2) == (0, 2)
        assert Outbox.objects.filter(attempts=0).count() == 1

    def test_loop_survives_errors_and_stops_on_sigterm(self, monkeypatch, capsys):
        from apps.leads.management.commands import send_notifications as cmd

        calls = {"process": 0, "sleep": []}
        handlers = {}

        def flaky_process_due():
            calls["process"] += 1
            if calls["process"] == 1:
                raise RuntimeError("database is locked")
            return (0, 0)

        def fake_sleep(seconds):
            calls["sleep"].append(seconds)
            if len(calls["sleep"]) == 2:
                handlers["term"](15, None)  # systemd присылает SIGTERM

        monkeypatch.setattr(cmd, "process_due", flaky_process_due)
        monkeypatch.setattr(cmd.time, "sleep", fake_sleep)
        monkeypatch.setattr(cmd.signal, "signal", lambda sig, handler: handlers.__setitem__("term", handler))

        call_command("send_notifications", "--loop", "--interval", "0.5")

        assert calls["process"] == 2, "после ошибки цикл продолжился"
        assert calls["sleep"] == [0.5, 0.5]

    def test_send_notifications_command_one_pass(self, rsps, clock, capsys):
        rsps.post(TG_URL, status=200)
        _due(clock)
        _due(clock, channel=Outbox.Channel.EMAIL)

        call_command("send_notifications")

        assert "Отправлено: 2, с ошибкой (будет повтор): 0" in capsys.readouterr().out
        assert Outbox.objects.filter(status=Outbox.Status.SENT).count() == 2
