"""Создание заявки: заявка сохраняется всегда; серверный пересчёт цены; снимок конфигурации; очередь; обезличивание."""
from datetime import date
from decimal import Decimal

import pytest

from apps.leads.models import Lead, Outbox
from apps.leads.services import anonymize_leads, build_configuration, create_lead, enqueue_lead_notifications, hash_ip
from tests.factories import (
    make_color,
    make_full_motorcycle,
    make_lead,
    make_motorcycle,
    make_outbox,
    make_rate,
    make_site_settings,
)

pytestmark = pytest.mark.django_db

NAME, PHONE = "Иван Петров", "+79123456789"


def lead_data(**overrides) -> dict:
    return {"kind": "callback", "name": NAME, "phone": PHONE, "message": "", "way": "", "options": (),
            "color": "", "page": "/catalog/", "model": "", "motorcycle": None, "is_spam": False, **overrides}


def model_data(moto, **overrides) -> dict:
    return lead_data(kind="model", model=moto.slug, motorcycle=moto, **overrides)


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
        assert hash_ip(None) == hash_ip("")


class TestBuildConfiguration:
    def test_no_model_no_slug_is_empty(self):
        assert build_configuration(lead_data()) == ({}, None)

    def test_missing_model_reports_error(self):
        config, total = build_configuration(lead_data(model="ghost-bike"))

        assert config == {"error": "Модель не найдена или снята с публикации — уточните у клиента"}
        assert "ghost-bike" not in repr(config), "текст клиента не попадает в уведомления"
        assert total is None

    def test_full_snapshot(self, priced):
        make_color(code="black", name="Чёрный")  # не в списке цветов модели — не подходит
        variant = priced.variants.get(label="8 kW 150Ah")

        config, total = build_configuration(model_data(
            priced, variant=variant.id, options=(f"abs_{priced.pk}", f"usb_{priced.pk}"),
            color=f"red_{priced.pk}", client_total=5))

        assert config == {
            "rate": "90.0000", "rate_date": "2026-11-07", "rate_source": "cbr_xml", "markup_rub": 100_000,
            "step": 1000, "client_total": 5, "color": "Красный", "included": ["USB"],
            "variant": "8 kW 150Ah", "options": ["ABS"], "options_on_request": [], "on_request": False,
        }
        assert total == 244_000  # 135 000 + 100 000 + 9 000

    def test_color_restricted_to_model_colors(self, priced):
        make_color(code="black", name="Чёрный")
        config, _ = build_configuration(model_data(priced, color="black"))
        assert config["color"] == ""

    def test_any_color_when_model_has_none(self, clock):
        moto = make_motorcycle()
        moto.variants.create(label="V", battery_ah=1, price_usd=Decimal("1"))
        make_color(code="black", name="Чёрный")

        config, _ = build_configuration(model_data(moto, color="black"))

        assert config["color"] == "Чёрный"

    def test_other_color(self, priced):
        config, _ = build_configuration(model_data(priced, color="other"))
        assert config["color"] == "Другой — согласовать"

    def test_defaults_to_first_variant(self, priced):
        config, total = build_configuration(model_data(priced))
        assert config["variant"] == priced.variants.first().label
        assert total == 190_000

    def test_stale_variant_reports_error(self, priced):
        other = make_full_motorcycle()

        config, total = build_configuration(model_data(priced, variant=other.variants.first().id))

        assert config["error"].startswith("Конфигурацию нужно уточнить")
        assert "variant" not in config
        assert config["rate"] == "90.0000", "контекст цены сохраняется и при ошибке"
        assert total is None

    def test_stale_option_reports_error(self, priced):
        config, total = build_configuration(model_data(priced, options=("turbo",)))
        assert config["error"].startswith("Конфигурацию нужно уточнить") and "turbo" in config["error"]
        assert total is None

    def test_model_without_variants(self, clock):
        config, total = build_configuration(model_data(make_motorcycle()))
        assert config["error"] == "Конфигурацию нужно уточнить: у модели нет вариантов"
        assert total is None

    def test_price_on_request(self, clock):
        moto = make_motorcycle()
        moto.variants.create(label="V", battery_ah=100, price_usd=None)

        config, total = build_configuration(model_data(moto))

        assert config["on_request"] is True and total is None


class TestCreateLead:
    def test_callback_lead(self, clock, settings):
        lead = create_lead(lead_data(), "10.0.0.1")

        assert lead.status == Lead.Status.NEW
        assert lead.kind == Lead.Kind.CALLBACK
        assert lead.config == {} and lead.total_rub is None and lead.model_name == ""
        assert lead.contact_way == Lead.Way.CALL
        assert lead.consent_version == settings.CONSENT_VERSION
        assert lead.consent_at == clock.current
        assert lead.ip_hash == hash_ip("10.0.0.1")
        assert lead.page == "/catalog/"

    def test_server_recomputes_total_and_ignores_client_total(self, priced):
        variant = priced.variants.get(label="5 kW 100Ah")

        lead = create_lead(model_data(priced, variant=variant.id, options=(f"abs_{priced.pk}",), client_total=1),
                           "1.1.1.1")

        assert lead.total_rub == 199_000  # 90 000 + 100 000 наценка + 9 000 ABS
        assert lead.config["client_total"] == 1
        assert lead.model_name == "Storm X" and lead.motorcycle == priced

    def test_spam_saved_with_status_and_no_outbox(self, priced):
        lead = create_lead(model_data(priced, is_spam=True), "1.1.1.1")

        assert Lead.objects.get(pk=lead.pk).status == Lead.Status.SPAM
        assert lead.notifications.count() == 0

    def test_missing_model_saved_and_notified(self, clock):
        lead = create_lead(lead_data(kind="model", model="ghost-bike"), "1.1.1.1")

        assert lead.pk is not None
        assert lead.config["error"] == "Модель не найдена или снята с публикации — уточните у клиента"
        assert lead.total_rub is None
        assert lead.model_name == ""
        assert lead.notifications.count() == 2

    def test_client_supplied_slug_not_echoed_into_notifications(self, clock):
        lead = create_lead(lead_data(kind="model", model="evil-link-example-com"), "1.1.1.1")

        assert all("evil-link" not in o.body and "evil-link" not in o.subject for o in lead.notifications.all())

    def test_quote_error_still_saves_lead(self, priced):
        other = make_full_motorcycle()

        lead = create_lead(model_data(priced, variant=other.variants.first().id), "1.1.1.1")

        lead.refresh_from_db()
        assert lead.status == Lead.Status.NEW
        assert lead.config["error"].startswith("Конфигурацию нужно уточнить")
        assert lead.total_rub is None
        assert lead.notifications.count() == 2

    def test_outbox_rows_for_telegram_and_email(self, priced, clock):
        lead = create_lead(model_data(priced), "1.1.1.1")

        rows = {o.channel: o for o in lead.notifications.all()}
        assert set(rows) == {Outbox.Channel.TELEGRAM, Outbox.Channel.EMAIL}
        assert all(o.status == Outbox.Status.PENDING and o.attempts == 0 for o in rows.values())
        assert all(o.next_attempt_at == clock.current and o.locked_until is None for o in rows.values())
        assert rows["email"].subject == f"Заявка №{lead.pk}: Storm X"
        assert NAME in rows["email"].body and PHONE in rows["email"].body

    def test_telegram_text_has_no_personal_data_by_default(self, priced):
        lead = create_lead(model_data(priced, message="секрет"), "1.1.1.1")

        body = lead.notifications.get(channel="telegram").body
        assert "Иван" not in body and "Петров" not in body
        assert PHONE not in body and "912" not in body
        assert "секрет" not in body
        assert "Контакты клиента — в админке" in body
        assert f"Новая заявка №{lead.pk}" in body and "Storm X" in body

    def test_telegram_text_contains_pd_when_enabled(self, priced, settings):
        settings.TELEGRAM = {**settings.TELEGRAM, "INCLUDE_PD": True}

        lead = create_lead(model_data(priced, way="messenger"), "1.1.1.1")

        body = lead.notifications.get(channel="telegram").body
        assert f"Клиент: {NAME}, {PHONE} (Написать в мессенджер)" in body

    def test_telegram_text_shows_warning_on_config_error(self, clock):
        lead = create_lead(lead_data(kind="model", model="ghost-bike"), "1.1.1.1")

        body = lead.notifications.get(channel="telegram").body
        assert "⚠ Модель не найдена или снята с публикации — уточните у клиента" in body

    def test_telegram_text_escapes_html(self, clock, settings):
        settings.TELEGRAM = {**settings.TELEGRAM, "INCLUDE_PD": True}
        moto = make_motorcycle(name="<b>Bike</b>")
        moto.variants.create(label="<i>V</i>", battery_ah=1, price_usd=Decimal("1"))

        lead = create_lead(model_data(moto, name="O'Neil"), "1.1.1.1")

        body = lead.notifications.get(channel="telegram").body
        assert "&lt;b&gt;Bike&lt;/b&gt;" in body and "&lt;i&gt;V&lt;/i&gt;" in body
        assert "O&#x27;Neil" in body

    def test_lead_and_outbox_in_same_transaction(self, priced, monkeypatch):
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


class TestAnonymizeLeads:
    def test_clears_pd_and_outbox_bodies(self, clock):
        target = make_lead(message="позвоните", ip_hash="abc", manager_note="клиент Иван, перезвонить")
        other = make_lead(name="Пётр")
        make_outbox(lead=target, body="Имя: Иван, +79123456789")
        untouched = make_outbox(lead=other, body="Имя: Пётр")

        count = anonymize_leads(Lead.objects.filter(pk=target.pk))

        assert count == 1
        target.refresh_from_db()
        assert (target.name, target.phone, target.message, target.ip_hash) == ("—", "—", "", "")
        assert target.manager_note == ""
        assert target.anonymized_at == clock.current
        assert target.notifications.get().body == "[обезличено]"
        untouched.refresh_from_db()
        assert untouched.body == "Имя: Пётр"
        other.refresh_from_db()
        assert other.name == "Пётр"

    def test_empty_queryset(self):
        assert anonymize_leads(Lead.objects.none()) == 0
