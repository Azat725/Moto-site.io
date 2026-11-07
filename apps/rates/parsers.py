"""Разбор ответов ЦБ РФ. Чистые функции: байты/JSON → ParsedRate."""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from defusedxml import ElementTree
from defusedxml.common import DefusedXmlException

MAX_RESPONSE_BYTES = 512 * 1024


class RateParseError(ValueError):
    pass


@dataclass(frozen=True)
class ParsedRate:
    currency: str
    value: Decimal
    effective_date: date
    source: str


def _decimal(text: str) -> Decimal:
    try:
        value = Decimal(text.strip().replace(",", "."))
    except (InvalidOperation, AttributeError) as exc:
        raise RateParseError(f"Некорректное число: {text!r}") from exc
    if not value.is_finite():
        raise RateParseError(f"Некорректное число: {text!r}")
    return value


def parse_cbr_xml(payload: bytes, currency: str = "USD") -> ParsedRate:
    """XML_daily.asp: кодировка windows-1251, Value с запятой, учитываем Nominal."""
    if len(payload) > MAX_RESPONSE_BYTES:
        raise RateParseError("Слишком большой ответ")
    if b"<!DOCTYPE" in payload.upper() or b"<!ENTITY" in payload.upper():
        raise RateParseError("DTD в ответе запрещён")
    try:
        root = ElementTree.fromstring(payload, forbid_dtd=True)
    except (ElementTree.ParseError, DefusedXmlException) as exc:
        raise RateParseError("Некорректный XML") from exc
    try:
        effective = datetime.strptime(root.attrib["Date"], "%d.%m.%Y").date()
    except (KeyError, ValueError) as exc:
        raise RateParseError("Нет даты курса") from exc
    for valute in root.iter("Valute"):
        if (valute.findtext("CharCode") or "").strip() == currency:
            nominal = _decimal(valute.findtext("Nominal") or "1")
            value = _decimal(valute.findtext("Value") or "")
            if nominal <= 0:
                raise RateParseError("Некорректный номинал")
            return ParsedRate(currency, (value / nominal).quantize(Decimal("0.0001")), effective, "cbr_xml")
    raise RateParseError(f"В ответе нет валюты {currency}")


def parse_cbr_json(payload: bytes, currency: str = "USD") -> ParsedRate:
    """daily_json.js (зеркало ЦБ): {"Date": "...", "Valute": {"USD": {"Nominal": 1, "Value": 81.12}}}."""
    if len(payload) > MAX_RESPONSE_BYTES:
        raise RateParseError("Слишком большой ответ")
    try:
        data = json.loads(payload.decode("utf-8"))
        item = data["Valute"][currency]
        effective = datetime.fromisoformat(data["Date"]).date()
    except (ValueError, KeyError, TypeError, UnicodeDecodeError) as exc:
        raise RateParseError("Некорректный JSON курса") from exc
    nominal = _decimal(str(item.get("Nominal", 1)))
    value = _decimal(str(item.get("Value", "")))
    if nominal <= 0:
        raise RateParseError("Некорректный номинал")
    return ParsedRate(currency, (value / nominal).quantize(Decimal("0.0001")), effective, "cbr_json")
