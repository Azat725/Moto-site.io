"""Получение и выбор актуального курса USD/RUB."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

import requests
from django.conf import settings
from django.utils import timezone

from .models import Rate
from .parsers import ParsedRate, RateParseError, parse_cbr_json, parse_cbr_xml

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CurrentRate:
    value: Decimal
    effective_date: date | None
    source: str
    is_stale: bool


@dataclass(frozen=True)
class RefreshResult:
    ok: bool
    message: str
    rate: Rate | None = None


def _fetch(url: str, params: dict | None = None) -> bytes:
    conf = settings.RATES
    response = requests.get(url, params=params, timeout=conf["TIMEOUT"], headers={"User-Agent": "ivax-moto-rate/1.0"})
    response.raise_for_status()
    return response.content


def fetch_from_source(source: str) -> ParsedRate:
    conf = settings.RATES
    if source == "cbr_xml":
        today = timezone.localdate().strftime("%d/%m/%Y")
        return parse_cbr_xml(_fetch(conf["CBR_XML_URL"], {"date_req": today}), conf["CURRENCY"])
    if source == "cbr_json":
        return parse_cbr_json(_fetch(conf["CBR_JSON_URL"]), conf["CURRENCY"])
    raise RateParseError(f"Неизвестный источник курса: {source}")


def last_accepted(currency: str = "USD") -> Rate | None:
    return Rate.objects.filter(currency=currency, accepted=True).order_by("-effective_date", "-fetched_at").first()


def _confirmed_by_previous_rejection(parsed: ParsedRate) -> bool:
    """Большой скачок принимаем, если предыдущая (отклонённая) попытка дала почти тот же курс."""
    last = Rate.objects.filter(currency=parsed.currency).order_by("-fetched_at").first()
    return bool(last and not last.accepted and abs(last.value - parsed.value) / parsed.value * 100 <= 1)


def _validate(parsed: ParsedRate, previous: Rate | None) -> str:
    """Пустая строка — курс принят; иначе причина отказа."""
    conf = settings.RATES
    if not conf["MIN"] <= parsed.value <= conf["MAX"]:
        return f"Курс {parsed.value} вне допустимого диапазона {conf['MIN']}–{conf['MAX']}"
    if previous is not None and previous.value > 0:
        jump = abs(parsed.value - previous.value) / previous.value * 100
        if jump > conf["MAX_JUMP_PCT"] and not _confirmed_by_previous_rejection(parsed):
            return f"Скачок курса {jump:.1f}% больше допустимых {conf['MAX_JUMP_PCT']}%"
    return ""


def refresh_rate() -> RefreshResult:
    """Пробует источники по порядку; сохраняет первый удачный ответ (принятый или отклонённый проверкой)."""
    errors: list[str] = []
    previous = last_accepted(settings.RATES["CURRENCY"])
    for source in settings.RATES["SOURCES"]:
        try:
            parsed = fetch_from_source(source)
        except (requests.RequestException, RateParseError) as exc:
            errors.append(f"{source}: {exc}")
            logger.warning("Источник курса %s недоступен: %s", source, exc)
            continue
        reason = _validate(parsed, previous)
        rate = Rate.objects.create(
            currency=parsed.currency, value=parsed.value, effective_date=parsed.effective_date,
            source=parsed.source, accepted=not reason, note=reason,
        )
        if reason:
            logger.error("Курс отклонён: %s", reason)
            return RefreshResult(False, reason, rate)
        return RefreshResult(True, f"Курс обновлён: {rate}", rate)
    return RefreshResult(False, "Не удалось получить курс: " + "; ".join(errors))


def current_rate(site=None) -> CurrentRate:
    """Курс для расчёта цен: ручной → последний принятый → запасной из настроек."""
    from apps.catalog.models import SiteSettings

    site = site or SiteSettings.load()
    if site.rate_mode == SiteSettings.RateMode.MANUAL and site.manual_rate:
        return CurrentRate(site.manual_rate, None, "manual", False)
    rate = last_accepted(settings.RATES["CURRENCY"])
    if rate is None:
        return CurrentRate(settings.RATES["FALLBACK"], None, "fallback", True)
    age = (timezone.localdate() - rate.effective_date).days
    return CurrentRate(rate.value, rate.effective_date, rate.source, age > settings.RATES["STALE_DAYS"])
