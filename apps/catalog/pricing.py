"""Чистые функции расчёта цены (без обращения к БД).

Формула (одинаковая на сервере и в браузере):
  компонент = round_half_up(цена_$ × курс × 100) копеек;
  к компоненту варианта прибавляется наценка;
  итог = сумма компонентов, округлённая ВВЕРХ до шага (в рублях).
В браузер передаются только готовые компоненты в копейках — без цен поставщика и наценки.
"""
from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal


@dataclass(frozen=True)
class PriceContext:
    rate: Decimal
    markup_rub: int
    step: int
    rate_date: date | None = None
    rate_source: str = ""

    def __post_init__(self) -> None:
        if self.rate <= 0:
            raise ValueError("Курс должен быть положительным")
        if self.markup_rub < 0:
            raise ValueError("Наценка не может быть отрицательной")
        if self.step <= 0:
            raise ValueError("Шаг округления должен быть положительным")


def to_kopecks(usd: Decimal, rate: Decimal) -> int:
    return int((usd * rate * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def variant_kopecks(price_usd: Decimal | None, ctx: PriceContext) -> int | None:
    if price_usd is None:
        return None
    return to_kopecks(price_usd, ctx.rate) + ctx.markup_rub * 100


def option_kopecks(price_usd: Decimal | None, ctx: PriceContext) -> int:
    return 0 if price_usd is None else to_kopecks(price_usd, ctx.rate)


def ceil_to_step(kopecks: int, step: int) -> int:
    if step <= 0:
        raise ValueError("Шаг округления должен быть положительным")
    unit = step * 100
    return -(-kopecks // unit) * step


def total_rub(variant_kop: int | None, option_kops: Iterable[int], step: int) -> int | None:
    if variant_kop is None:
        return None
    return ceil_to_step(variant_kop + sum(option_kops), step)


def display_rub(kopecks: int) -> int:
    """Округление вверх до рубля — для отображения доплаты за опцию."""
    return -(-kopecks // 100)
