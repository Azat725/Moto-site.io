"""Создание заявки: серверный пересчёт цены, снимок конфигурации, очередь уведомлений."""
from datetime import date
from decimal import Decimal

import pytest

from apps.leads.models import Lead, Outbox
from apps.leads.services import create_lead, enqueue_lead_notifications, hash_ip
from tests.factories import make_color, make_full_motorcycle, make_motorcycle, make_rate, make_site_settings

pytestmark = pytest.mark.django_db

NAME, PHONE = "Иван Петров", "+79123456789"


def lead_data(**overrides) -> dict:
    return {"kind": "callback", "name": NAME, "phone": PHONE, "message": "", "way": "", "options": (),
            "color": "", "page": "/catalog/", **overrides}


@pytest.fixture
def priced(clock):
    make_site_settings(markup_rub=100_000, rounding_step=1000)
    make_rate("90.0000", effective_date=date(2026, 11, 7))
    return make_full_motorcycle(name="Storm X")


class TestHashIp:
    def test_deterministic_and_salted(self, settings):
        first = hash_ip("10.0.0.1")
        assert first == hash_ip("10.0.0.1")
        assert first != hash_ip("10.0.0.2")
        assert len(first) == 64 and "10.0.0.1" not in first
        settings.IP_HASH_SALT = "other"
        assert hash_ip("10.0.0.1") != first

    def test_empty_ip(self):
        assert len(hash_ip("")) == 64
        assert hash_ip(None) == hash_ip("")


class TestCreateLead:
    def test_callback_lead_without_model(self, clock, settings):
        lead = create_lead(lead_data(), "10.0.0.1")

        assert lead.kind == Lead.Kind.CALLBACK
        assert lead.config == {}
        assert lead.total_rub is None
        assert lead.model_name == ""
        assert lead.contact_way == Lead.Way.CALL
        assert lead.consent_version == settings.CONSENT_VERSION
        assert lead.consent_at == clock.current
        assert lead.ip_hash == hash_ip("10.0.0.1")
        assert lead.page == "/catalog/"

    def test_server_recomputes_total_and_ignores_client_total(self, priced):
        variant = priced.variants.get(label="5 kW 100Ah")

        lead = create_lead(lead_data(kind="model", motorcycle=priced, variant=variant.id,
                                     options=(f"abs_{priced.pk}",), client_total=1), "1.1.1.1")

        assert lead.total_rub == 199_000  # 90 000 + 100 000 наценка + 9 000 ABS
        assert lead.config["client_total"] == 1

    def test_config_snapshot_fields(self, priced):
        make_color(code="black", name="Чёрный")
        variant = priced.variants.get(label="8 kW 150Ah")

        lead = create_lead(lead_data(kind="model", motorcycle=priced, variant=variant.id,
                                     options=(f"abs_{priced.pk}", f"usb_{priced.pk}"), color="black"), "1.1.1.1")

        assert lead.model_name == "Storm X"
        assert lead.motorcycle == priced
        assert lead.config == {
            "variant": "8 kW 150Ah", "options": ["ABS"], "included": ["USB"], "color": "Чёрный",
            "rate": "90.0000", "rate_date": "2026-11-07", "rate_source": "cbr_xml", "markup_rub": 100_000,
            "step": 1000, "client_total": None, "on_request": False,
        }
        assert lead.total_rub == 244_000  # 135 000 + 100 000 + 9 000

    def test_defaults_to_first_variant(self, priced):
        lead = create_lead(lead_data(kind="model", motorcycle=priced), "1.1.1.1")

        assert lead.config["variant"] == priced.variants.first().label
        assert lead.total_rub == 190_000

    def test_other_color(self, priced):
        lead = create_lead(lead_data(kind="model", motorcycle=priced, color="other"), "1.1.1.1")
        assert lead.config["color"] == "Другой — согласовать"

    def test_model_without_variants(self, clock):
        moto = make_motorcycle()

        lead = create_lead(lead_data(kind="model", motorcycle=moto), "1.1.1.1")

        assert lead.config == {"note": "у модели нет вариантов"}
        assert lead.total_rub is None

    def test_price_on_request(self, clock):
        moto = make_motorcycle()
        moto.variants.create(label="V", battery_ah=100, price_usd=None)

        lead = create_lead(lead_data(kind="model", motorcycle=moto), "1.1.1.1")

        assert lead.total_rub is None
        assert lead.config["on_request"] is True

    def test_foreign_variant_raises_value_error_and_writes_nothing(self, priced):
        other = make_full_motorcycle()

        with pytest.raises(ValueError, match="вариант"):
            create_lead(lead_data(kind="model", motorcycle=priced, variant=other.variants.first().id), "1.1.1.1")

        assert Lead.objects.count() == 0 and Outbox.objects.count() == 0

    def test_unknown_option_raises_value_error(self, priced):
        with pytest.raises(ValueError, match="turbo"):
            create_lead(lead_data(kind="model", motorcycle=priced, options=("turbo",)), "1.1.1.1")

    def test_outbox_rows_for_telegram_and_email(self, priced, clock):
        lead = create_lead(lead_data(kind="model", motorcycle=priced), "1.1.1.1")

        rows = {o.channel: o for o in lead.notifications.all()}
        assert set(rows) == {Outbox.Channel.TELEGRAM, Outbox.Channel.EMAIL}
        assert all(o.status == Outbox.Status.PENDING and o.attempts == 0 for o in rows.values())
        assert all(o.next_attempt_at == clock.current for o in rows.values())
        assert rows["email"].subject == f"Заявка №{lead.pk}: Storm X"
        assert NAME in rows["email"].body and PHONE in rows["email"].body

    def test_telegram_text_has_no_personal_data_by_default(self, priced):
        lead = create_lead(lead_data(kind="model", motorcycle=priced, message="секрет"), "1.1.1.1")

        body = lead.notifications.get(channel="telegram").body
        assert NAME not in body and "Иван" not in body
        assert PHONE not in body and "912" not in body
        assert "секрет" not in body
        assert "Контакты клиента — в админке" in body
        assert f"Новая заявка №{lead.pk}" in body
        assert "Storm X" in body

    def test_telegram_text_contains_pd_when_enabled(self, priced, settings):
        settings.TELEGRAM = {**settings.TELEGRAM, "INCLUDE_PD": True}

        lead = create_lead(lead_data(kind="model", motorcycle=priced, way="messenger"), "1.1.1.1")

        body = lead.notifications.get(channel="telegram").body
        assert f"Клиент: {NAME}, {PHONE} (Написать в мессенджер)" in body

    def test_telegram_text_escapes_html(self, clock, settings):
        settings.TELEGRAM = {**settings.TELEGRAM, "INCLUDE_PD": True}
        moto = make_motorcycle(name="<b>Bike</b>")
        moto.variants.create(label="<i>V</i>", battery_ah=1, price_usd=Decimal("1"))

        lead = create_lead(lead_data(kind="model", motorcycle=moto, name="O'Neil"), "1.1.1.1")

        body = lead.notifications.get(channel="telegram").body
        assert "&lt;b&gt;Bike&lt;/b&gt;" in body and "&lt;i&gt;V&lt;/i&gt;" in body
        assert "O&#x27;Neil" in body

    def test_outbox_created_in_same_transaction(self, priced, monkeypatch):
        def boom(lead):
            raise RuntimeError("queue down")

        monkeypatch.setattr("apps.leads.services.enqueue_lead_notifications", boom)

        with pytest.raises(RuntimeError):
            create_lead(lead_data(), "1.1.1.1")

        assert Lead.objects.count() == 0, "заявка откатывается вместе с очередью"

    def test_no_channels_configured(self, clock, settings):
        settings.TELEGRAM = {**settings.TELEGRAM, "BOT_TOKEN": ""}
        settings.LEAD_NOTIFY_EMAILS = []

        lead = create_lead(lead_data(), "1.1.1.1")

        assert lead.notifications.count() == 0
        assert enqueue_lead_notifications(lead) == []
