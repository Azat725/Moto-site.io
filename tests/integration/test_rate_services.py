"""Получение курса (responses вместо сети), выбор текущего курса и команда update_rate."""
from datetime import date, datetime, timezone as dt_timezone
from decimal import Decimal

import pytest
import requests
from django.core.management import CommandError, call_command

from apps.catalog.models import SiteSettings
from apps.rates.models import Rate
from apps.rates.parsers import RateParseError
from apps.rates.services import current_rate, fetch_from_source, last_accepted, refresh_rate
from tests.factories import make_rate, make_site_settings
from tests.fixtures.cbr import JSON_URL, XML_URL, cbr_json, cbr_xml

pytestmark = pytest.mark.django_db


def _xml_ok(rsps, value="81,1234"):
    rsps.get(XML_URL, body=cbr_xml(usd_value=value), status=200)


def _json_ok(rsps, value=81.12):
    rsps.get(JSON_URL, body=cbr_json(usd_value=value), status=200)


class TestFetchFromSource:
    def test_xml_source_sends_today_date_and_user_agent(self, rsps, clock):
        _xml_ok(rsps)

        parsed = fetch_from_source("cbr_xml")

        assert parsed.source == "cbr_xml"
        request = rsps.calls[0].request
        assert "date_req=07%2F11%2F2026" in request.url
        assert request.headers["User-Agent"].startswith("ivax-moto-rate")

    def test_json_source(self, rsps):
        _json_ok(rsps)
        assert fetch_from_source("cbr_json").value == Decimal("81.1200")

    def test_unknown_source_raises(self):
        with pytest.raises(RateParseError, match="Неизвестный источник"):
            fetch_from_source("ecb")

    def test_http_error_propagates(self, rsps):
        rsps.get(XML_URL, status=503)
        with pytest.raises(requests.HTTPError):
            fetch_from_source("cbr_xml")


class TestRefreshRate:
    def test_first_source_success_stores_accepted_rate(self, rsps, clock):
        _xml_ok(rsps)

        result = refresh_rate()

        assert result.ok is True
        assert result.rate.value == Decimal("81.1234")
        assert result.rate.source == "cbr_xml"
        assert result.rate.accepted is True
        assert "Курс обновлён" in result.message
        assert len(rsps.calls) == 1, "второй источник не должен опрашиваться"

    def test_first_source_http_error_falls_back_to_second(self, rsps, clock):
        rsps.get(XML_URL, status=500)
        _json_ok(rsps, value=82.5)

        result = refresh_rate()

        assert result.ok is True
        assert result.rate.source == "cbr_json"
        assert result.rate.value == Decimal("82.5000")
        assert Rate.objects.count() == 1

    def test_first_source_unparseable_falls_back_to_second(self, rsps, clock):
        rsps.get(XML_URL, body=b"<html>maintenance</html>", status=200)
        _json_ok(rsps)

        result = refresh_rate()

        assert result.ok is True
        assert result.rate.source == "cbr_json"

    def test_connection_error_falls_back(self, rsps, clock):
        rsps.get(XML_URL, body=requests.ConnectionError("down"))
        _json_ok(rsps)

        assert refresh_rate().rate.source == "cbr_json"

    def test_both_sources_fail_returns_not_ok_without_rows(self, rsps, clock):
        rsps.get(XML_URL, status=502)
        rsps.get(JSON_URL, body=b"{broken", status=200)

        result = refresh_rate()

        assert result.ok is False
        assert result.rate is None
        assert "cbr_xml" in result.message and "cbr_json" in result.message
        assert Rate.objects.count() == 0

    @pytest.mark.parametrize("value", ["19,9999", "500,0001", "0"])
    def test_out_of_range_rate_stored_but_not_accepted(self, rsps, clock, value):
        _xml_ok(rsps, value=value)

        result = refresh_rate()

        assert result.ok is False
        assert result.rate.accepted is False
        assert "диапазона" in result.rate.note
        assert last_accepted() is None

    def test_rejected_rate_does_not_try_next_source(self, rsps, clock):
        _xml_ok(rsps, value="1000,00")
        _json_ok(rsps)

        refresh_rate()

        assert len(rsps.calls) == 1

    def test_jump_over_limit_vs_previous_rejected(self, rsps, clock):
        make_rate("80.0000", effective_date=date(2026, 11, 6))
        _xml_ok(rsps, value="96,1000")  # +20.125 %

        result = refresh_rate()

        assert result.ok is False
        assert result.rate.accepted is False
        assert "Скачок" in result.rate.note
        assert last_accepted().value == Decimal("80.0000")

    def test_jump_exactly_at_limit_accepted(self, rsps, clock):
        make_rate("80.0000", effective_date=date(2026, 11, 6))
        _xml_ok(rsps, value="96,0000")  # ровно 20 %

        assert refresh_rate().ok is True

    def test_downward_jump_rejected_too(self, rsps, clock):
        make_rate("100.0000", effective_date=date(2026, 11, 6))
        _xml_ok(rsps, value="79,0000")

        assert refresh_rate().ok is False

    def test_jump_compared_with_last_accepted_not_last_rejected(self, rsps, clock):
        make_rate("80.0000", effective_date=date(2026, 11, 5))
        make_rate("200.0000", effective_date=date(2026, 11, 6), accepted=False)
        _xml_ok(rsps, value="85,0000")

        assert refresh_rate().ok is True

    @pytest.mark.xfail(
        reason="BUG: services.py:58 NaN rate from source makes `MIN <= value` raise decimal.InvalidOperation; "
               "refresh_rate crashes instead of rejecting/falling back", strict=True, raises=ArithmeticError,
    )
    def test_nan_rate_from_source_does_not_crash(self, rsps, clock, settings):
        settings.RATES = {**settings.RATES, "SOURCES": ["cbr_json"]}
        rsps.get(JSON_URL, body=b'{"Date": "2026-11-07T11:30:00+03:00", "Valute": {"USD": {"Value": NaN}}}')

        result = refresh_rate()

        assert result.ok is False


class TestCurrentRate:
    def test_manual_mode_uses_manual_rate(self, clock):
        make_rate("90.0000")
        make_site_settings(rate_mode=SiteSettings.RateMode.MANUAL, manual_rate=Decimal("95.5000"))

        rate = current_rate()

        assert rate.value == Decimal("95.5000")
        assert rate.source == "manual"
        assert rate.is_stale is False
        assert rate.effective_date == date(2026, 11, 7)

    def test_manual_mode_without_value_falls_back_to_auto(self, clock):
        make_rate("90.0000")
        make_site_settings(rate_mode=SiteSettings.RateMode.MANUAL, manual_rate=None)

        assert current_rate().source == "cbr_xml"

    def test_uses_last_accepted_rate(self, clock):
        make_rate("88.0000", effective_date=date(2026, 11, 5))
        make_rate("89.0000", effective_date=date(2026, 11, 6), source="cbr_json")
        make_rate("300.0000", effective_date=date(2026, 11, 7), accepted=False)

        rate = current_rate()

        assert rate.value == Decimal("89.0000")
        assert rate.source == "cbr_json"
        assert rate.effective_date == date(2026, 11, 6)
        assert rate.is_stale is False

    def test_ignores_other_currencies(self, clock):
        make_rate("94.0000", currency="EUR")
        assert current_rate().source == "fallback"

    def test_fallback_when_no_rates(self, clock, settings):
        rate = current_rate()

        assert rate.value == settings.RATES["FALLBACK"]
        assert rate.source == "fallback"
        assert rate.effective_date is None
        assert rate.is_stale is True

    def test_stale_after_more_than_stale_days(self, clock):
        make_rate("90.0000", effective_date=date(2026, 11, 3))  # 4 дня назад
        assert current_rate().is_stale is True

    def test_not_stale_at_exactly_stale_days(self, clock):
        make_rate("90.0000", effective_date=date(2026, 11, 4))  # 3 дня назад
        assert current_rate().is_stale is False

    def test_staleness_uses_local_moscow_date(self, clock):
        make_rate("90.0000", effective_date=date(2026, 11, 4))
        clock.set(datetime(2026, 11, 7, 21, 30, tzinfo=dt_timezone.utc))  # уже 8 ноября в Москве
        assert current_rate().is_stale is True


class TestUpdateRateCommand:
    def test_success_prints_message(self, rsps, clock, capsys):
        _xml_ok(rsps)

        call_command("update_rate")

        assert "Курс обновлён" in capsys.readouterr().out
        assert Rate.objects.filter(accepted=True).count() == 1

    def test_failure_raises_command_error(self, rsps, clock):
        rsps.get(XML_URL, status=500)
        rsps.get(JSON_URL, status=500)

        with pytest.raises(CommandError, match="Не удалось получить курс"):
            call_command("update_rate")

    def test_soft_failure_only_warns(self, rsps, clock, capsys):
        rsps.get(XML_URL, status=500)
        rsps.get(JSON_URL, status=500)

        call_command("update_rate", "--soft")

        assert "Не удалось получить курс" in capsys.readouterr().err
