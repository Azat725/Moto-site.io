"""Простые фабрики тестовых данных (без factory_boy): каждая функция создаёт и возвращает объект в БД."""
from __future__ import annotations

import itertools
from datetime import date
from decimal import Decimal

from apps.catalog.models import Color, Motorcycle, MotorcycleOption, OptionDef, SiteSettings, Variant
from apps.leads.models import Lead, Outbox
from apps.rates.models import Rate
from apps.reviews.models import Review

_seq = itertools.count(1)


def _n() -> int:
    return next(_seq)


def make_site_settings(**overrides) -> SiteSettings:
    site = SiteSettings.load()
    for key, value in {"markup_rub": 100_000, "rounding_step": 1000, **overrides}.items():
        setattr(site, key, value)
    site.save()
    return site


def make_motorcycle(**overrides) -> Motorcycle:
    n = _n()
    fields = {"slug": f"model-{n}", "name": f"Model {n}", "is_published": True, **overrides}
    return Motorcycle.objects.create(**fields)


def make_variant(motorcycle: Motorcycle, **overrides) -> Variant:
    n = _n()
    fields = {"label": f"Variant {n}", "battery_ah": 100, "price_usd": Decimal("1000.00"), "sort_order": n,
              **overrides}
    return Variant.objects.create(motorcycle=motorcycle, **fields)


def make_option_def(**overrides) -> OptionDef:
    n = _n()
    fields = {"code": f"opt_{n}", "name": f"Option {n}", **overrides}
    return OptionDef.objects.create(**fields)


def make_motorcycle_option(motorcycle: Motorcycle, option: OptionDef | None = None, **overrides) -> MotorcycleOption:
    fields = {"status": MotorcycleOption.Status.OPTIONAL, "price_usd": Decimal("100.00"), **overrides}
    return MotorcycleOption.objects.create(motorcycle=motorcycle, option=option or make_option_def(), **fields)


def make_color(**overrides) -> Color:
    n = _n()
    fields = {"code": f"color_{n}", "name": f"Color {n}", "hex": "#E10600", **overrides}
    return Color.objects.create(**fields)


def make_rate(value: str | Decimal = "90.0000", **overrides) -> Rate:
    fields = {"currency": "USD", "value": Decimal(value), "effective_date": date(2026, 11, 7), "source": "cbr_xml",
              "accepted": True, **overrides}
    return Rate.objects.create(**fields)


def make_full_motorcycle(**overrides) -> Motorcycle:
    """Модель с двумя вариантами, платной и включённой опциями и одним цветом."""
    moto = make_motorcycle(**overrides)
    make_variant(moto, label="5 kW 100Ah", price_usd=Decimal("1000.00"), sort_order=1)
    make_variant(moto, label="8 kW 150Ah", battery_ah=150, price_usd=Decimal("1500.00"), sort_order=2)
    make_motorcycle_option(moto, make_option_def(code=f"abs_{moto.pk}", name="ABS"), price_usd=Decimal("100.00"))
    make_motorcycle_option(moto, make_option_def(code=f"usb_{moto.pk}", name="USB"),
                           status=MotorcycleOption.Status.INCLUDED, price_usd=None)
    moto.colors.add(make_color(code=f"red_{moto.pk}", name="Красный"))
    return moto


def make_lead(**overrides) -> Lead:
    fields = {"name": "Иван", "phone": "+79123456789", "consent_at": "2026-11-07T12:00:00Z",
              "consent_version": "2026-11-07", **overrides}
    return Lead.objects.create(**fields)


def make_outbox(**overrides) -> Outbox:
    fields = {"channel": Outbox.Channel.TELEGRAM, "subject": "Заявка", "body": "Текст",
              "next_attempt_at": "2026-11-07T12:00:00Z", **overrides}
    return Outbox.objects.create(**fields)


def make_review(**overrides) -> Review:
    fields = {"display_name": "Анна", "city": "Казань", "rating": 5, "text": "Отличный мотоцикл, всем доволен!",
              "consent_at": "2026-11-07T12:00:00Z", "publication_consent_at": "2026-11-07T12:00:00Z",
              "status": Review.Status.APPROVED, **overrides}
    return Review.objects.create(**fields)
