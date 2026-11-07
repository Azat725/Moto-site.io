"""Сборщики ответов ЦБ РФ для тестов (формат как у XML_daily.asp и daily_json.js)."""
from __future__ import annotations

import json

XML_URL = "https://www.cbr.ru/scripts/XML_daily.asp"
JSON_URL = "https://www.cbr-xml-daily.ru/daily_json.js"


def cbr_xml(usd_value: str = "81,1234", usd_nominal: str = "1", date: str = "07.11.2026",
            include_usd: bool = True) -> bytes:
    """Ответ XML_daily.asp в windows-1251 (с кириллицей в Name, чтобы проверить декодирование)."""
    usd = (
        '<Valute ID="R01235"><NumCode>840</NumCode><CharCode>USD</CharCode>'
        f"<Nominal>{usd_nominal}</Nominal><Name>Доллар США</Name><Value>{usd_value}</Value></Valute>"
    ) if include_usd else ""
    text = (
        '<?xml version="1.0" encoding="windows-1251"?>'
        f'<ValCurs Date="{date}" name="Foreign Currency Market">'
        '<Valute ID="R01239"><NumCode>978</NumCode><CharCode>EUR</CharCode><Nominal>1</Nominal>'
        "<Name>Евро</Name><Value>94,5000</Value></Valute>"
        '<Valute ID="R01820"><NumCode>392</NumCode><CharCode>JPY</CharCode><Nominal>100</Nominal>'
        "<Name>Иен</Name><Value>53,2100</Value></Valute>"
        f"{usd}</ValCurs>"
    )
    return text.encode("cp1251")


def cbr_json(usd_value=81.12, usd_nominal=1, date: str = "2026-11-07T11:30:00+03:00",
             include_usd: bool = True) -> bytes:
    valute = {"EUR": {"CharCode": "EUR", "Nominal": 1, "Value": 94.5},
              "JPY": {"CharCode": "JPY", "Nominal": 100, "Value": 53.21}}
    if include_usd:
        valute["USD"] = {"CharCode": "USD", "Nominal": usd_nominal, "Value": usd_value}
    return json.dumps({"Date": date, "Valute": valute}).encode("utf-8")
