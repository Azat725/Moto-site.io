"""Цены и предложения по моделям с учётом БД (настройки, курс)."""
from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field

from django.db.models import Prefetch, QuerySet

from . import pricing
from .models import Motorcycle, MotorcycleOption, SiteSettings, Variant


class QuoteError(ValueError):
    pass


@dataclass(frozen=True)
class VariantOffer:
    id: int
    label: str
    kopecks: int | None
    price_rub: int | None


@dataclass(frozen=True)
class OptionOffer:
    code: str
    name: str
    description: str
    included: bool
    kopecks: int
    plus_rub: int
    on_request: bool = False


@dataclass(frozen=True)
class Offer:
    variants: tuple[VariantOffer, ...]
    options: tuple[OptionOffer, ...]
    step: int
    min_price_rub: int | None
    max_price_rub: int | None

    def as_json(self) -> dict:
        """Данные для конфигуратора: только рублёвые компоненты, без цен поставщика и наценки."""
        return {
            "step": self.step,
            "variants": [{"id": v.id, "label": v.label, "kop": v.kopecks} for v in self.variants],
            "options": [{"code": o.code, "kop": o.kopecks, "included": o.included} for o in self.options],
        }


@dataclass(frozen=True)
class Quote:
    variant: Variant
    options: tuple[MotorcycleOption, ...]
    total_rub: int | None
    ctx: pricing.PriceContext = field(repr=False)

    @property
    def on_request(self) -> bool:
        return self.total_rub is None


def current_context() -> pricing.PriceContext:
    from apps.rates.services import current_rate

    site = SiteSettings.load()
    rate = current_rate(site)
    return pricing.PriceContext(
        rate=rate.value, markup_rub=site.markup_rub, step=site.rounding_step,
        rate_date=rate.effective_date, rate_source=rate.source,
    )


def published_motorcycles() -> QuerySet[Motorcycle]:
    return (
        Motorcycle.objects.filter(is_published=True)
        .prefetch_related(
            "variants", "photos", "colors",
            Prefetch("options", queryset=MotorcycleOption.objects.select_related("option")),
        )
    )


def build_offer(moto: Motorcycle, ctx: pricing.PriceContext) -> Offer:
    variants = tuple(
        VariantOffer(
            id=v.id, label=v.label, kopecks=(kop := pricing.variant_kopecks(v.price_usd, ctx)),
            price_rub=None if kop is None else pricing.ceil_to_step(kop, ctx.step),
        )
        for v in moto.variants.all()
    )
    options = tuple(
        OptionOffer(
            code=o.option.code, name=o.option.name, description=o.option.description, included=o.is_included,
            kopecks=0 if o.is_included else (kop := pricing.option_kopecks(o.price_usd, ctx)),
            plus_rub=0 if o.is_included else pricing.display_rub(kop),
            on_request=not o.is_included and o.price_usd is None,
        )
        for o in moto.options.all()
    )
    prices = [v.price_rub for v in variants if v.price_rub is not None]
    return Offer(variants, options, ctx.step, min(prices, default=None), max(prices, default=None))


def quote(moto: Motorcycle, ctx: pricing.PriceContext, variant_id: int, option_codes: Iterable[str]) -> Quote:
    """Серверный расчёт выбранной комплектации. Включённые опции не стоят денег, неизвестные — ошибка."""
    variant = next((v for v in moto.variants.all() if v.id == variant_id), None)
    if variant is None:
        raise QuoteError("Неизвестный вариант комплектации")
    by_code = {o.option.code: o for o in moto.options.all()}
    chosen_codes = tuple(dict.fromkeys(option_codes))
    unknown = [code for code in chosen_codes if code not in by_code]
    if unknown:
        raise QuoteError("Неизвестные опции: " + ", ".join(unknown))
    chosen = tuple(by_code[code] for code in chosen_codes if not by_code[code].is_included)
    kops = [pricing.option_kopecks(o.price_usd, ctx) for o in chosen]
    total = pricing.total_rub(pricing.variant_kopecks(variant.price_usd, ctx), kops, ctx.step)
    return Quote(variant=variant, options=chosen, total_rub=total, ctx=ctx)
