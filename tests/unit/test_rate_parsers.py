"""Разбор ответов ЦБ РФ: XML (windows-1251) и JSON-зеркало."""
from datetime import date
from decimal import Decimal

import pytest

from apps.rates.parsers import MAX_RESPONSE_BYTES, ParsedRate, RateParseError, parse_cbr_json, parse_cbr_xml
from tests.fixtures.cbr import cbr_json, cbr_xml


class TestParseCbrXml:
    def test_parses_windows_1251_payload_with_comma_decimal(self):
        result = parse_cbr_xml(cbr_xml(usd_value="81,1234"))

        assert result == ParsedRate("USD", Decimal("81.1234"), date(2026, 11, 7), "cbr_xml")

    def test_payload_really_is_windows_1251(self):
        payload = cbr_xml()
        assert "Доллар".encode("cp1251") in payload
        with pytest.raises(UnicodeDecodeError):
            payload.decode("utf-8")

    def test_divides_by_nominal(self):
        result = parse_cbr_xml(cbr_xml(usd_value="8112,3400", usd_nominal="100"))

        assert result.value == Decimal("81.1234")

    def test_other_currency_with_nominal_100(self):
        result = parse_cbr_xml(cbr_xml(), currency="JPY")

        assert result.currency == "JPY"
        assert result.value == Decimal("0.5321")

    def test_value_is_quantized_to_4_places(self):
        result = parse_cbr_xml(cbr_xml(usd_value="100,00", usd_nominal="3"))

        assert result.value == Decimal("33.3333")

    def test_missing_usd_raises(self):
        with pytest.raises(RateParseError, match="USD"):
            parse_cbr_xml(cbr_xml(include_usd=False))

    @pytest.mark.parametrize("payload", [b"", b"<ValCurs", b"not xml at all", b"<a><b></a>"])
    def test_malformed_xml_raises(self, payload):
        with pytest.raises(RateParseError):
            parse_cbr_xml(payload)

    @pytest.mark.parametrize("marker", [b"<!DOCTYPE", b"<!doctype", b"<!ENTITY"])
    def test_dtd_and_entities_rejected(self, marker):
        payload = (b'<?xml version="1.0"?>' + marker + b' lol [<!ENTITY a "x">]>'
                   b'<ValCurs Date="07.11.2026"><Valute><CharCode>USD</CharCode>'
                   b"<Nominal>1</Nominal><Value>&a;</Value></Valute></ValCurs>")
        with pytest.raises(RateParseError, match="DTD"):
            parse_cbr_xml(payload)

    def test_oversize_payload_rejected_before_parsing(self):
        payload = cbr_xml() + b" " * MAX_RESPONSE_BYTES
        with pytest.raises(RateParseError, match="большой"):
            parse_cbr_xml(payload)

    def test_payload_exactly_at_limit_is_parsed(self):
        base = cbr_xml()
        payload = base + b" " * (MAX_RESPONSE_BYTES - len(base))
        assert len(payload) == MAX_RESPONSE_BYTES
        assert parse_cbr_xml(payload).value == Decimal("81.1234")

    @pytest.mark.parametrize("date_attr", ["", "2026-11-07", "32.13.2026"])
    def test_bad_or_missing_date_raises(self, date_attr):
        with pytest.raises(RateParseError, match="даты"):
            parse_cbr_xml(cbr_xml(date=date_attr))

    def test_no_date_attribute_raises(self):
        payload = b'<ValCurs><Valute><CharCode>USD</CharCode><Value>1</Value></Valute></ValCurs>'
        with pytest.raises(RateParseError, match="даты"):
            parse_cbr_xml(payload)

    @pytest.mark.parametrize("value", ["", "abc", "81;12"])
    def test_bad_value_raises(self, value):
        with pytest.raises(RateParseError, match="число"):
            parse_cbr_xml(cbr_xml(usd_value=value))

    @pytest.mark.parametrize("nominal", ["0", "-1"])
    def test_non_positive_nominal_raises(self, nominal):
        with pytest.raises(RateParseError, match="номинал"):
            parse_cbr_xml(cbr_xml(usd_nominal=nominal))

    def test_missing_nominal_defaults_to_one(self):
        payload = (b'<ValCurs Date="07.11.2026"><Valute><CharCode>USD</CharCode>'
                   b"<Value>80,5</Value></Valute></ValCurs>")
        assert parse_cbr_xml(payload).value == Decimal("80.5000")


class TestParseCbrJson:
    def test_parses_normal_payload(self):
        result = parse_cbr_json(cbr_json(usd_value=81.12))

        assert result == ParsedRate("USD", Decimal("81.1200"), date(2026, 11, 7), "cbr_json")

    def test_divides_by_nominal(self):
        result = parse_cbr_json(cbr_json(), currency="JPY")

        assert result.value == Decimal("0.5321")

    def test_missing_nominal_defaults_to_one(self):
        payload = b'{"Date": "2026-11-07T11:30:00+03:00", "Valute": {"USD": {"Value": 80.5}}}'
        assert parse_cbr_json(payload).value == Decimal("80.5000")

    @pytest.mark.parametrize("payload", [b"", b"{", b"[1, 2]", b"null", b'{"Valute": {}}',
                                         b'{"Date": "bad", "Valute": {"USD": {"Value": 1}}}',
                                         b"\xff\xfe\x00garbage"])
    def test_bad_json_raises(self, payload):
        with pytest.raises(RateParseError, match="JSON"):
            parse_cbr_json(payload)

    def test_missing_currency_raises(self):
        with pytest.raises(RateParseError):
            parse_cbr_json(cbr_json(include_usd=False))

    def test_zero_nominal_raises(self):
        with pytest.raises(RateParseError, match="номинал"):
            parse_cbr_json(cbr_json(usd_nominal=0))

    def test_missing_value_raises(self):
        payload = b'{"Date": "2026-11-07T11:30:00+03:00", "Valute": {"USD": {"Nominal": 1}}}'
        with pytest.raises(RateParseError):
            parse_cbr_json(payload)

    def test_oversize_payload_rejected(self):
        with pytest.raises(RateParseError, match="большой"):
            parse_cbr_json(b" " * (MAX_RESPONSE_BYTES + 1))

    def test_non_object_currency_entry_raises_parse_error(self):
        payload = b'{"Date": "2026-11-07T11:30:00+03:00", "Valute": {"USD": 81.12}}'
        with pytest.raises(RateParseError):
            parse_cbr_json(payload)

    def test_nan_value_rejected(self):
        payload = b'{"Date": "2026-11-07T11:30:00+03:00", "Valute": {"USD": {"Nominal": 1, "Value": NaN}}}'
        with pytest.raises(RateParseError):
            parse_cbr_json(payload)

    def test_infinite_value_rejected(self):
        payload = b'{"Date": "2026-11-07T11:30:00+03:00", "Valute": {"USD": {"Nominal": 1, "Value": Infinity}}}'
        with pytest.raises(RateParseError):
            parse_cbr_json(payload)


class TestNonFiniteXml:
    @pytest.mark.parametrize("value", ["NaN", "Infinity", "-Infinity", "sNaN"])
    def test_non_finite_xml_value_rejected(self, value):
        with pytest.raises(RateParseError, match="число"):
            parse_cbr_xml(cbr_xml(usd_value=value))

    def test_non_finite_nominal_rejected(self):
        with pytest.raises(RateParseError):
            parse_cbr_xml(cbr_xml(usd_nominal="Infinity"))


class TestDefusedXml:
    def test_dtd_hidden_from_byte_scan_still_rejected(self):
        """UTF-16 прячет «<!DOCTYPE» от поиска по байтам — defusedxml (forbid_dtd) всё равно отклоняет."""
        text = ('<?xml version="1.0" encoding="UTF-16"?><!DOCTYPE x [<!ENTITY a "b">]>'
                '<ValCurs Date="07.11.2026"><Valute><CharCode>USD</CharCode><Value>&a;</Value></Valute></ValCurs>')
        payload = text.encode("utf-16")
        assert b"<!DOCTYPE" not in payload.upper()

        with pytest.raises(RateParseError):
            parse_cbr_xml(payload)
