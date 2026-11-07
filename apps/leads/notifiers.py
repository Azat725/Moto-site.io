"""Тексты и отправка уведомлений менеджеру: Telegram (по умолчанию без персональных данных) и e-mail."""
from __future__ import annotations

import html
from datetime import timedelta

import requests
from django.conf import settings
from django.core.mail import EmailMessage
from django.utils import timezone

from .models import Lead, Outbox


def _fmt_rub(value: int | None) -> str:
    return "по запросу" if value is None else f"{value:,}".replace(",", " ") + " ₽"


def _config_lines(lead: Lead) -> list[str]:
    cfg = lead.config or {}
    lines = []
    if lead.model_name:
        lines.append(f"Модель: {lead.model_name}")
    if cfg.get("variant"):
        lines.append(f"Комплектация: {cfg['variant']}")
    if cfg.get("options"):
        lines.append("Опции: " + ", ".join(cfg["options"]))
    if cfg.get("color"):
        lines.append(f"Цвет: {cfg['color']}")
    if lead.model_name:
        rate_note = f" (курс {cfg.get('rate', '')} на {cfg.get('rate_date', '')})" if cfg.get("rate") else ""
        lines.append(f"Итого: {_fmt_rub(lead.total_rub)}{rate_note}")
    return lines


def telegram_enabled() -> bool:
    conf = settings.TELEGRAM
    return bool(conf["BOT_TOKEN"] and conf["CHAT_ID"])


def telegram_text(lead: Lead) -> str:
    """HTML для Telegram. Имя и телефон добавляются только при TELEGRAM_INCLUDE_PD=true (трансграничная передача)."""
    parts = [f"<b>Новая заявка №{lead.pk}</b> · {html.escape(lead.get_kind_display())}"]
    parts += [html.escape(line) for line in _config_lines(lead)]
    if settings.TELEGRAM["INCLUDE_PD"]:
        parts.append(f"Клиент: {html.escape(lead.name)}, {html.escape(lead.phone)} ({html.escape(lead.get_contact_way_display())})")
    else:
        parts.append("Контакты клиента — в админке сайта и в письме.")
    admin_url = f"{settings.SITE_DOMAIN}/{settings.ADMIN_PATH}leads/lead/{lead.pk}/change/"
    parts.append(f'<a href="{html.escape(admin_url)}">Открыть заявку</a>')
    return "\n".join(parts)


def email_subject(lead: Lead) -> str:
    title = lead.model_name or lead.get_kind_display()
    return f"Заявка №{lead.pk}: {title}".replace("\r", " ").replace("\n", " ")


def email_text(lead: Lead) -> str:
    lines = [
        f"Новая заявка №{lead.pk} от {timezone.localtime(lead.created_at):%d.%m.%Y %H:%M}",
        f"Тип: {lead.get_kind_display()}",
        f"Имя: {lead.name}",
        f"Телефон: {lead.phone}",
        f"Способ связи: {lead.get_contact_way_display()}",
        *_config_lines(lead),
    ]
    if lead.message:
        lines.append(f"Комментарий: {lead.message}")
    lines.append(f"Страница: {lead.page or '—'}")
    return "\n".join(lines)


def send_telegram(item: Outbox) -> None:
    conf = settings.TELEGRAM
    url = f"{conf['API_BASE']}/bot{conf['BOT_TOKEN']}/sendMessage"
    payload = {"chat_id": conf["CHAT_ID"], "text": item.body, "parse_mode": "HTML", "disable_web_page_preview": True}
    response = requests.post(url, json=payload, timeout=conf["TIMEOUT"])
    if response.status_code != 200:
        raise RuntimeError(f"Telegram ответил {response.status_code}")


def send_email(item: Outbox) -> None:
    if not settings.LEAD_NOTIFY_EMAILS:
        raise RuntimeError("Не заданы LEAD_NOTIFY_EMAILS")
    EmailMessage(item.subject, item.body, to=settings.LEAD_NOTIFY_EMAILS).send(fail_silently=False)


SENDERS = {Outbox.Channel.TELEGRAM: send_telegram, Outbox.Channel.EMAIL: send_email}


def deliver(item: Outbox) -> bool:
    """Одна попытка доставки. Возвращает True при успехе; статус и расписание повтора сохраняются."""
    try:
        SENDERS[item.channel](item)
    except Exception as exc:  # любые сетевые/SMTP ошибки — повторим позже
        item.attempts += 1
        item.last_error = f"{type(exc).__name__}: {exc}"[:500]
        if item.attempts >= settings.OUTBOX_MAX_ATTEMPTS:
            item.status = Outbox.Status.DEAD
        else:
            schedule = settings.OUTBOX_BACKOFF_SECONDS
            delay = schedule[min(item.attempts - 1, len(schedule) - 1)]
            item.next_attempt_at = timezone.now() + timedelta(seconds=delay)
        item.save(update_fields=["attempts", "last_error", "status", "next_attempt_at"])
        return False
    item.attempts += 1
    item.status = Outbox.Status.SENT
    item.sent_at = timezone.now()
    item.last_error = ""
    item.save(update_fields=["attempts", "status", "sent_at", "last_error"])
    return True


def process_due(limit: int = 20) -> tuple[int, int]:
    due = Outbox.objects.filter(status=Outbox.Status.PENDING, next_attempt_at__lte=timezone.now()).order_by("id")[:limit]
    results = [deliver(item) for item in due]
    return sum(results), len(results) - sum(results)
