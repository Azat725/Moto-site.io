"""POST /api/leads/: JSON и обычная форма, антиспам без потери заявки, лимит по БД, демо-режим, IP за прокси,
защита публичных адресов от загрузок и больших тел; команда purge_leads."""
from datetime import date, timedelta

import pytest
from django.core.management import call_command
from django.test import RequestFactory, override_settings

from apps.leads.forms import issue_form_token
from apps.leads.models import Lead, Outbox
from apps.leads.ratelimit import client_ip, limit_key, over_limit
from apps.leads.services import hash_ip
from apps.pages.middleware import PUBLIC_BODY_LIMIT
from apps.reviews.models import Review
from tests.factories import make_full_motorcycle, make_lead, make_outbox, make_rate, make_review, make_site_settings
from tests.fixtures.http import FORM_CT, post_form

pytestmark = pytest.mark.django_db

URL = "/api/leads/"


def payload(**overrides) -> dict:
    return {"kind": "callback", "name": "Иван", "phone": "8 912 345-67-89", "consent": "on",
            "form_token": issue_form_token(), **overrides}


@pytest.fixture
def moto(clock):
    make_site_settings(markup_rub=100_000, rounding_step=1000)
    make_rate("90.0000", effective_date=date(2026, 11, 7))
    return make_full_motorcycle(name="Storm X")


class TestCreateLeadView:
    def test_json_success_returns_201_with_server_total(self, client, moto):
        variant = moto.variants.get(label="5 kW 100Ah")

        response = post_form(client, URL, payload(model=moto.slug, variant=variant.id, options=f"abs_{moto.pk}",
                                                  client_total=150_000))

        assert response.status_code == 201
        body = response.json()
        assert body["success"] is True
        assert body["data"]["total_rub"] == 199_000
        assert body["data"]["price_changed"] is True
        lead = Lead.objects.get(pk=body["data"]["id"])
        assert lead.status == Lead.Status.NEW
        assert lead.total_rub == 199_000 and lead.phone == "+79123456789"
        assert lead.notifications.count() == 2

    def test_price_changed_false_when_client_matches(self, client, moto):
        response = post_form(client, URL, payload(model=moto.slug, client_total=190_000))
        assert response.json()["data"]["price_changed"] is False

    def test_validation_error_400_with_fields(self, client):
        response = post_form(client, URL, payload(name="1", phone="12", consent="", model="Шторм"))

        assert response.status_code == 400
        body = response.json()
        assert body["success"] is False
        assert set(body["fields"]) == {"name", "phone", "consent", "model"}
        assert Lead.objects.count() == 0

    def test_honeypot_returns_success_and_saves_spam_lead(self, client):
        response = post_form(client, URL, payload(website="http://spam"))

        assert response.status_code == 201
        assert response.json()["success"] is True
        assert Lead.objects.get().status == Lead.Status.SPAM
        assert Outbox.objects.count() == 0

    def test_missing_token_saved_as_spam(self, client):
        data = payload()
        del data["form_token"]

        assert post_form(client, URL, data).status_code == 201
        assert Lead.objects.get().status == Lead.Status.SPAM

    def test_stale_config_still_saves_lead(self, client, moto):
        response = post_form(client, URL, payload(model=moto.slug, options="turbo"))

        assert response.status_code == 201
        assert response.json()["data"]["total_rub"] is None
        assert Lead.objects.get().config["error"].startswith("Конфигурацию нужно уточнить")

    def test_unknown_model_still_saves_lead(self, client, clock):
        response = post_form(client, URL, payload(model="ghost"))

        assert response.status_code == 201
        lead = Lead.objects.get()
        assert lead.config["error"].startswith("Модель не найдена") and lead.model_name == ""

    def test_lead_ip_hash_uses_limit_key(self, client):
        post_form(client, URL, payload(), REMOTE_ADDR="2001:db8:1:2:3:4:5:6")
        assert Lead.objects.get().ip_hash == hash_ip("2001:db8:1:2::/64")

    def test_non_json_success_redirects_to_thanks(self, client):
        response = post_form(client, URL, payload(), json=False)
        assert response.status_code == 302 and response["Location"] == "/thanks/"

    def test_non_json_error_redirects_with_flag(self, client):
        response = post_form(client, URL, payload(phone="1"), json=False)
        assert response.status_code == 302 and response["Location"] == "/thanks/?error=1"

    def test_get_not_allowed(self, client):
        assert client.get(URL).status_code == 405

    @override_settings(SITE_MODE="demo")
    def test_demo_mode_rejects_with_403(self, client):
        response = post_form(client, URL, payload())

        assert response.status_code == 403
        assert "Демо" in response.json()["error"]
        assert Lead.objects.count() == 0

    def test_no_delivery_inside_request(self, client, rsps, django_capture_on_commit_callbacks):
        with django_capture_on_commit_callbacks(execute=True) as callbacks:
            post_form(client, URL, payload())

        assert callbacks == []
        assert len(rsps.calls) == 0, "уведомления отправляет только send_notifications"
        assert Outbox.objects.filter(status=Outbox.Status.PENDING).count() == 2


class TestLeadRateLimit:
    def test_429_after_limit(self, client, settings, clock):
        settings.LEAD_RATE_LIMIT = (2, 600)

        codes = [post_form(client, URL, payload()).status_code for _ in range(3)]

        assert codes == [201, 201, 429]
        assert Lead.objects.count() == 2
        assert "Слишком много" in post_form(client, URL, payload()).json()["error"]

    def test_invalid_submissions_do_not_consume_limit(self, client, settings, clock):
        settings.LEAD_RATE_LIMIT = (1, 600)
        for _ in range(5):
            assert post_form(client, URL, payload(phone="1")).status_code == 400

        assert post_form(client, URL, payload()).status_code == 201

    def test_spam_leads_count_towards_limit(self, client, settings, clock):
        settings.LEAD_RATE_LIMIT = (2, 600)
        post_form(client, URL, payload(website="x"))
        post_form(client, URL, payload(website="x"))

        assert post_form(client, URL, payload()).status_code == 429

    def test_window_expires(self, client, settings, clock):
        settings.LEAD_RATE_LIMIT = (1, 600)
        assert post_form(client, URL, payload()).status_code == 201
        assert post_form(client, URL, payload()).status_code == 429

        clock.set(clock.current + timedelta(seconds=601))

        assert post_form(client, URL, payload()).status_code == 201

    def test_limit_is_per_ip(self, client, settings, clock):
        settings.LEAD_RATE_LIMIT = (1, 600)

        assert post_form(client, URL, payload(), REMOTE_ADDR="10.0.0.1").status_code == 201
        assert post_form(client, URL, payload(), REMOTE_ADDR="10.0.0.1").status_code == 429
        assert post_form(client, URL, payload(), REMOTE_ADDR="10.0.0.2").status_code == 201

    def test_ipv6_same_64_shares_limit(self, client, settings, clock):
        settings.LEAD_RATE_LIMIT = (1, 600)

        assert post_form(client, URL, payload(), REMOTE_ADDR="2001:db8:aa:bb::1").status_code == 201
        assert post_form(client, URL, payload(), REMOTE_ADDR="2001:db8:aa:bb:ffff::9").status_code == 429
        assert post_form(client, URL, payload(), REMOTE_ADDR="2001:db8:aa:cc::1").status_code == 201

    def test_limit_survives_cache_clear(self, client, settings, clock):
        from django.core.cache import cache

        settings.LEAD_RATE_LIMIT = (1, 600)
        post_form(client, URL, payload())
        cache.clear()

        assert post_form(client, URL, payload()).status_code == 429

    def test_trusted_proxy_limits_per_real_client(self, client, settings, clock):
        settings.TRUSTED_PROXY = True
        settings.TRUSTED_PROXY_IPS = ["127.0.0.1"]
        settings.LEAD_RATE_LIMIT = (1, 600)
        proxy = {"REMOTE_ADDR": "127.0.0.1"}

        assert post_form(client, URL, payload(), HTTP_X_REAL_IP="1.1.1.1", **proxy).status_code == 201
        assert post_form(client, URL, payload(), HTTP_X_REAL_IP="2.2.2.2", **proxy).status_code == 201
        assert post_form(client, URL, payload(), HTTP_X_REAL_IP="1.1.1.1", **proxy).status_code == 429

    def test_spoofed_header_from_untrusted_peer_ignored(self, client, settings, clock):
        settings.TRUSTED_PROXY = True
        settings.TRUSTED_PROXY_IPS = ["127.0.0.1"]
        settings.LEAD_RATE_LIMIT = (1, 600)
        attacker = {"REMOTE_ADDR": "203.0.113.5"}

        assert post_form(client, URL, payload(), HTTP_X_REAL_IP="1.1.1.1", **attacker).status_code == 201
        assert post_form(client, URL, payload(), HTTP_X_REAL_IP="9.9.9.9", **attacker).status_code == 429


class TestClientIp:
    rf = RequestFactory()

    def test_untrusted_proxy_setting_uses_remote_addr(self, settings):
        settings.TRUSTED_PROXY = False
        request = self.rf.get("/", REMOTE_ADDR="127.0.0.1", HTTP_X_REAL_IP="1.2.3.4")
        assert client_ip(request) == "127.0.0.1"

    def test_trusted_proxy_peer_uses_x_real_ip(self, settings):
        settings.TRUSTED_PROXY = True
        settings.TRUSTED_PROXY_IPS = ["127.0.0.1", "::1"]
        assert client_ip(self.rf.get("/", REMOTE_ADDR="::1", HTTP_X_REAL_IP=" 1.2.3.4 ")) == "1.2.3.4"

    def test_header_from_non_proxy_peer_ignored(self, settings):
        settings.TRUSTED_PROXY = True
        settings.TRUSTED_PROXY_IPS = ["127.0.0.1"]
        assert client_ip(self.rf.get("/", REMOTE_ADDR="198.51.100.7", HTTP_X_REAL_IP="1.2.3.4")) == "198.51.100.7"

    def test_x_forwarded_for_never_used(self, settings):
        settings.TRUSTED_PROXY = True
        settings.TRUSTED_PROXY_IPS = ["127.0.0.1"]
        request = self.rf.get("/", REMOTE_ADDR="127.0.0.1", HTTP_X_FORWARDED_FOR="5.6.7.8")
        assert client_ip(request) == "127.0.0.1"

    def test_blank_real_ip_falls_back(self, settings):
        settings.TRUSTED_PROXY = True
        settings.TRUSTED_PROXY_IPS = ["127.0.0.1"]
        assert client_ip(self.rf.get("/", REMOTE_ADDR="127.0.0.1", HTTP_X_REAL_IP="  ")) == "127.0.0.1"

    def test_no_remote_addr(self, settings):
        request = self.rf.get("/")
        request.META.pop("REMOTE_ADDR", None)
        assert client_ip(request) == ""


class TestLimitKey:
    @pytest.mark.parametrize("ip, expected", [
        ("10.0.0.1", "10.0.0.1"), ("2001:db8::1", "2001:db8::/64"),
        ("2001:db8:1:2:3:4:5:6", "2001:db8:1:2::/64"), ("", ""), ("garbage", "garbage"),
    ])
    def test_keys(self, ip, expected):
        assert limit_key(ip) == expected


class TestOverLimit:
    def test_counts_only_inside_window(self, clock):
        old = make_lead(ip_hash="h")
        Lead.objects.filter(pk=old.pk).update(created_at=clock.current - timedelta(seconds=700))
        make_lead(ip_hash="h")

        assert over_limit(Lead.objects.filter(ip_hash="h"), 2, 600) is False
        assert over_limit(Lead.objects.filter(ip_hash="h"), 1, 600) is True

    def test_empty(self, clock):
        assert over_limit(Lead.objects.none(), 1, 600) is False


class TestPublicUploadGuard:
    def test_multipart_to_public_endpoint_is_415(self, client):
        response = client.post(URL, payload(), HTTP_ACCEPT="application/json")  # dict → multipart
        assert response.status_code == 415
        assert Lead.objects.count() == 0

    def test_multipart_to_reviews_is_415(self, client):
        assert client.post("/reviews/submit/", {"text": "x"}).status_code == 415

    def test_body_over_64kb_is_413(self, client):
        response = post_form(client, URL, payload(message="я" * PUBLIC_BODY_LIMIT))
        assert response.status_code == 413

    def test_body_at_limit_passes_guard(self, client):
        data = {"x": "a" * (PUBLIC_BODY_LIMIT - 2)}
        response = client.post(URL, data="x=" + data["x"], content_type=FORM_CT)
        assert response.status_code != 413

    def test_bad_content_length_is_413(self, client):
        response = client.generic("POST", URL, b"a=1", content_type=FORM_CT, CONTENT_LENGTH="abc")
        assert response.status_code == 413

    def test_get_unaffected(self, client):
        assert client.get("/robots.txt").status_code == 200

    def test_admin_paths_unaffected(self, admin_client_logged, admin_prefix):
        response = admin_client_logged.post(admin_prefix + "catalog/motorcycle/import/", {})  # multipart
        assert response.status_code == 200

    def test_admin_login_multipart_not_blocked(self, client, admin_prefix):
        assert client.post(admin_prefix + "login/", {"username": "x", "password": "y"}).status_code != 415


class TestPurgeLeads:
    def test_anonymizes_only_old_leads(self, clock, settings, capsys):
        settings.LEAD_RETENTION_DAYS = 30
        old = make_lead(message="старое", manager_note="Иван просил перезвонить")
        Lead.objects.filter(pk=old.pk).update(created_at=clock.current - timedelta(days=31))
        make_outbox(lead=old, body="Телефон: +79123456789")
        fresh = make_lead()
        Lead.objects.filter(pk=fresh.pk).update(created_at=clock.current - timedelta(days=29))

        call_command("purge_leads")

        assert "Обезличено заявок: 1" in capsys.readouterr().out
        old.refresh_from_db()
        fresh.refresh_from_db()
        assert (old.name, old.phone, old.message, old.manager_note) == ("—", "—", "", "")
        assert old.anonymized_at == clock.current
        assert old.notifications.get().body == "[обезличено]"
        assert fresh.name == "Иван" and fresh.anonymized_at is None

    def test_already_anonymized_not_counted_again(self, clock, settings, capsys):
        settings.LEAD_RETENTION_DAYS = 1
        lead = make_lead(anonymized_at=clock.current - timedelta(days=5))
        Lead.objects.filter(pk=lead.pk).update(created_at=clock.current - timedelta(days=10))

        call_command("purge_leads")

        assert "Обезличено заявок: 0" in capsys.readouterr().out

    def test_deletes_old_rejected_reviews_only(self, clock, capsys):
        old_rejected = make_review(status=Review.Status.REJECTED)
        young_rejected = make_review(status=Review.Status.REJECTED)
        old_approved = make_review(status=Review.Status.APPROVED)
        old_pending = make_review(status=Review.Status.PENDING)
        Review.objects.filter(pk__in=[old_rejected.pk, old_approved.pk, old_pending.pk]).update(
            created_at=clock.current - timedelta(days=91))
        Review.objects.filter(pk=young_rejected.pk).update(created_at=clock.current - timedelta(days=89))

        call_command("purge_leads")

        assert "удалено отклонённых отзывов: 1" in capsys.readouterr().out
        assert set(Review.objects.values_list("pk", flat=True)) == {young_rejected.pk, old_approved.pk,
                                                                     old_pending.pk}
