"""Создание заявки: пересчёт цены на сервере, запись в БД и постановка уведомлений в очередь одной транзакцией."""
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


def _configuration(data: dict) -> tuple[dict, int | None]:
    moto = data.get("motorcycle")
    if moto is None:
        return {}, None
    ctx = current_context()
    variant_id = data.get("variant") or next((v.id for v in moto.variants.all()), None)
    if variant_id is None:
        return {"note": "у модели нет вариантов"}, None
    try:
        result = quote(moto, ctx, variant_id, data.get("options") or ())
    except QuoteError as exc:
        raise ValueError(str(exc)) from exc
    color_code = data.get("color") or ""
    color = Color.objects.filter(code=color_code).first()
    config = {
        "variant": result.variant.label,
        "options": [o.option.name for o in result.options],
        "included": [o.option.name for o in moto.options.all() if o.is_included],
        "color": color.name if color else ("Другой — согласовать" if color_code == "other" else ""),
        "rate": str(ctx.rate),
        "rate_date": ctx.rate_date.isoformat() if ctx.rate_date else "",
        "rate_source": ctx.rate_source,
        "markup_rub": ctx.markup_rub,
        "step": ctx.step,
        "client_total": data.get("client_total"),
        "on_request": result.on_request,
    }
    return config, result.total_rub


def create_lead(data: dict, ip: str) -> Lead:
    config, total = _configuration(data)
    moto = data.get("motorcycle")
    with transaction.atomic():
        lead = Lead.objects.create(
            kind=data.get("kind") or Lead.Kind.CALLBACK,
            name=data["name"],
            phone=data["phone"],
            message=data.get("message", ""),
            contact_way=data.get("way") or Lead.Way.CALL,
            motorcycle=moto,
            model_name=moto.name if moto else "",
            config=config,
            total_rub=total,
            consent_at=timezone.now(),
            consent_version=settings.CONSENT_VERSION,
            page=data.get("page", ""),
            ip_hash=hash_ip(ip),
        )
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
