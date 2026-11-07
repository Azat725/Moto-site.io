"""Подготовка данных для шаблонов (без побочных эффектов)."""
from __future__ import annotations

from django.conf import settings

from apps.catalog.models import Motorcycle
from apps.catalog.services import Offer, build_offer, current_context, published_motorcycles
from apps.reviews.models import Review

from .content import SAMPLE_REVIEWS


def card(moto: Motorcycle, offer: Offer) -> dict:
    photo = next(iter(moto.photos.all()), None)
    variants = list(moto.variants.all())
    max_range = max((v.range_max_km or moto.range_max_km for v in variants), default=moto.range_max_km)
    max_speed = max((v.top_speed_kmh or moto.top_speed_kmh for v in variants), default=moto.top_speed_kmh)
    powers = sorted({(v.motor_power_w or moto.motor_power_w) for v in variants} or {moto.motor_power_w})
    return {
        "moto": moto, "offer": offer, "photo": photo,
        "power_label": " / ".join(f"{p / 1000:g}" for p in powers) + " кВт",
        "power_max_kw": max(powers) / 1000, "powers_kw": " ".join(f"{p / 1000:g}" for p in powers),
        "max_range": max_range, "max_speed": max_speed,
        "battery_label": " / ".join(sorted({str(v.battery_ah) for v in variants}, key=int)) + " А·ч",
    }


def catalog_cards() -> tuple[list[dict], object]:
    ctx = current_context()
    cards = [card(m, build_offer(m, ctx)) for m in published_motorcycles()]
    return cards, ctx


def reviews_for(motorcycle: Motorcycle | None = None, limit: int = 6) -> tuple[list, bool]:
    """Одобренные отзывы; если их нет и разрешены образцы (демо) — образцы с пометкой «пример»."""
    qs = Review.objects.filter(status=Review.Status.APPROVED).select_related("motorcycle")
    if motorcycle is not None:
        qs = qs.filter(motorcycle=motorcycle)
    real = list(qs[:limit])
    if real or not settings.SHOW_SAMPLE_REVIEWS:
        return real, False
    return list(SAMPLE_REVIEWS), True


def filter_facets(cards: list[dict]) -> dict:
    types = [(code, label) for code, label in Motorcycle.Type.choices if any(c["moto"].type == code for c in cards)]
    lines = sorted({c["moto"].line for c in cards if c["moto"].line})
    powers = sorted({float(p) for c in cards for p in c["powers_kw"].split()})
    powers = [f"{p:g}" for p in powers]
    return {"types": types, "lines": lines, "powers": powers}
