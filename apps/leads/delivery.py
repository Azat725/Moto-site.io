"""Доставка уведомлений из очереди Outbox с захватом записи (без двойной отправки) и повторами."""
from __future__ import annotations

from datetime import timedelta

from django.conf import settings
from django.db.models import Q
from django.utils import timezone

from .models import Outbox
from .notifiers import SENDERS, NotifyError

LOCK_SECONDS = 120


def claim(item_id: int) -> bool:
    """Атомарно забирает запись в работу. Только один процесс получит True."""
    now = timezone.now()
    due = Q(status=Outbox.Status.PENDING, next_attempt_at__lte=now) | Q(status=Outbox.Status.SENDING, locked_until__lt=now)
    return Outbox.objects.filter(due, pk=item_id).update(
        status=Outbox.Status.SENDING, locked_until=now + timedelta(seconds=LOCK_SECONDS)
    ) == 1


def _fail(item: Outbox, error: str) -> None:
    attempts = item.attempts + 1
    schedule = settings.OUTBOX_BACKOFF_SECONDS
    dead = attempts >= settings.OUTBOX_MAX_ATTEMPTS
    Outbox.objects.filter(pk=item.pk).update(
        attempts=attempts, last_error=error[:500], locked_until=None,
        status=Outbox.Status.DEAD if dead else Outbox.Status.PENDING,
        next_attempt_at=timezone.now() + timedelta(seconds=schedule[min(attempts - 1, len(schedule) - 1)]),
    )


def deliver(item_id: int) -> bool:
    """Одна попытка доставки захваченной записи. True — отправлено."""
    if not claim(item_id):
        return False
    item = Outbox.objects.get(pk=item_id)
    try:
        SENDERS[item.channel](item)
    except NotifyError as exc:
        _fail(item, str(exc))
        return False
    except Exception as exc:  # сетевые/SMTP ошибки любого типа — повторим позже
        _fail(item, f"{type(exc).__name__}: {exc}")
        return False
    Outbox.objects.filter(pk=item.pk).update(
        status=Outbox.Status.SENT, attempts=item.attempts + 1, sent_at=timezone.now(), last_error="", locked_until=None
    )
    return True


def due_ids(limit: int = 20) -> list[int]:
    now = timezone.now()
    due = Q(status=Outbox.Status.PENDING, next_attempt_at__lte=now) | Q(status=Outbox.Status.SENDING, locked_until__lt=now)
    return list(Outbox.objects.filter(due).order_by("id").values_list("pk", flat=True)[:limit])


def process_due(limit: int = 20) -> tuple[int, int]:
    results = [deliver(pk) for pk in due_ids(limit)]
    return sum(results), len(results) - sum(results)
