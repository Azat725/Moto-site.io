"""Создание заявки: пересчёт цены на сервере, запись в БД и постановка уведомлений в очередь одной транзакцией.

Заявку с контактами не теряем никогда: устаревшая конфигурация или снятая с публикации модель сохраняются
с пометкой в config["error"], подозрение на спам — со статусом «Спам» и без уведомлений.
"""
from __future__ import annotations

import hashlib
import hmac

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.catalog.models import Color
from apps.catalog.services import QuoteError, current_context, quote

from . import notifiers
from .models import Lead, Outbox


def hash_ip(ip: str) -> str:
    return hmac.new(settings.IP_HASH_SALT.encode(), (ip or "").encode(), hashlib.sha256).hexdigest()


def _color_name(moto, code: str) -> str:
    if code == "other":
        return "Другой — согласовать"
    allowed = list(moto.colors.all()) or list(Color.objects.all())
    found = next((c for c in allowed if c.code == code), None)
    return found.name if found else ""


def build_configuration(data: dict) -> tuple[dict, int | None]:
    """Снимок конфигурации и итоговая цена. Ошибки не прерывают сохранение заявки."""
    moto = data.get("motorcycle")
    if moto is None:
        slug = data.get("model") or ""
        return ({"error": f"Модель «{slug}» не найдена или снята с публикации"} if slug else {}), None
    ctx = current_context()
    base = {"rate": str(ctx.rate), "rate_date": ctx.rate_date.isoformat() if ctx.rate_date else "",
            "rate_source": ctx.rate_source, "markup_rub": ctx.markup_rub, "step": ctx.step,
            "client_total": data.get("client_total"), "color": _color_name(moto, data.get("color") or ""),
            "included": [o.option.name for o in moto.options.all() if o.is_included]}
    variant_id = data.get("variant") or next((v.id for v in moto.variants.all()), None)
    try:
        if variant_id is None:
            raise QuoteError("у модели нет вариантов")
        result = quote(moto, ctx, variant_id, data.get("options") or ())
    except QuoteError as exc:
        return base | {"error": f"Конфигурацию нужно уточнить: {exc}"}, None
    return base | {"variant": result.variant.label, "options": [o.option.name for o in result.options],
                   "on_request": result.on_request}, result.total_rub


def create_lead(data: dict, ip: str) -> Lead:
    config, total = build_configuration(data)
    moto = data.get("motorcycle")
    is_spam = bool(data.get("is_spam"))
    with transaction.atomic():
        lead = Lead.objects.create(
            status=Lead.Status.SPAM if is_spam else Lead.Status.NEW,
            kind=data.get("kind") or Lead.Kind.CALLBACK,
            name=data["name"],
            phone=data["phone"],
            message=data.get("message", ""),
            contact_way=data.get("way") or Lead.Way.CALL,
            motorcycle=moto,
            model_name=moto.name if moto else (data.get("model") or "")[:80],
            config=config,
            total_rub=total,
            consent_at=timezone.now(),
            consent_version=settings.CONSENT_VERSION,
            page=data.get("page", ""),
            ip_hash=hash_ip(ip),
        )
        if not is_spam:
            enqueue_lead_notifications(lead)
    return lead


def enqueue_lead_notifications(lead: Lead) -> list[Outbox]:
    now = timezone.now()
    rows = []
    if notifiers.telegram_enabled():
        rows.append(Outbox(channel=Outbox.Channel.TELEGRAM, lead=lead, subject=f"Заявка №{lead.pk}",
                           body=notifiers.telegram_text(lead), next_attempt_at=now))
    if settings.LEAD_NOTIFY_EMAILS:
        rows.append(Outbox(channel=Outbox.Channel.EMAIL, lead=lead, subject=notifiers.email_subject(lead),
                           body=notifiers.email_text(lead), next_attempt_at=now))
    return Outbox.objects.bulk_create(rows)


def anonymize_leads(queryset) -> int:
    """Обезличивает заявки и тексты их уведомлений (там тоже были имя и телефон)."""
    with transaction.atomic():
        ids = list(queryset.values_list("pk", flat=True))
        Outbox.objects.filter(lead_id__in=ids).update(body="[обезличено]")
        return Lead.objects.filter(pk__in=ids).update(
            name="—", phone="—", message="", ip_hash="", anonymized_at=timezone.now()
        )
