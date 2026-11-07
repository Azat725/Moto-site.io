"""Админка: списки открываются, импорт CSV (предпросмотр → применение), выгрузки, действия."""
import csv
import io
from datetime import date
from decimal import Decimal

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from openpyxl import load_workbook

from apps.catalog.admin import copy_motorcycle
from apps.catalog.admin_import import SESSION_KEY
from apps.catalog.models import Motorcycle, MotorcycleOption, SiteSettings
from apps.leads.admin import csv_safe
from apps.leads.models import Lead, Outbox
from apps.rates.models import Rate
from apps.reviews.models import Review
from tests.factories import (
    make_full_motorcycle,
    make_lead,
    make_motorcycle,
    make_option_def,
    make_outbox,
    make_rate,
    make_review,
    make_site_settings,
)
from tests.fixtures.cbr import XML_URL, cbr_xml

pytestmark = pytest.mark.django_db

IMPORT_CSV = ("slug;name;type;published;variant_label;battery_ah;price_usd;opt:abs\r\n"
              "storm-x;Storm X;спорт;да;5 kW;100;1000;150\r\n"
              "storm-x;Storm X;спорт;да;8 kW;150;1500;включено\r\n").encode("utf-8-sig")


@pytest.fixture
def seeded(clock):
    make_site_settings()
    make_rate("90.0000", effective_date=date(2026, 11, 7))
    moto = make_full_motorcycle(name="Storm X")
    lead = make_lead(model_name="Storm X", total_rub=199_000, config={"variant": "5 kW", "options": ["ABS"]})
    make_outbox(lead=lead)
    make_review()
    return moto, lead


def url(prefix: str, tail: str) -> str:
    return prefix + tail


class TestChangelists:
    @pytest.mark.parametrize("tail", [
        "", "catalog/motorcycle/", "catalog/optiondef/", "catalog/color/", "catalog/sitesettings/",
        "leads/lead/", "leads/outbox/", "reviews/review/", "rates/rate/",
    ])
    def test_changelist_200(self, admin_client_logged, admin_prefix, seeded, tail):
        assert admin_client_logged.get(url(admin_prefix, tail)).status_code == 200

    def test_motorcycle_changelist_shows_price_from(self, admin_client_logged, admin_prefix, seeded):
        response = admin_client_logged.get(url(admin_prefix, "catalog/motorcycle/"))
        assert "190 000 ₽" in response.content.decode()

    def test_change_pages_200(self, admin_client_logged, admin_prefix, seeded):
        moto, lead = seeded
        pages = [f"catalog/motorcycle/{moto.pk}/change/", f"leads/lead/{lead.pk}/change/", "catalog/sitesettings/1/change/",
                 f"leads/outbox/{lead.notifications.first().pk}/change/"]
        for tail in pages:
            assert admin_client_logged.get(url(admin_prefix, tail)).status_code == 200, tail

    def test_motorcycle_change_shows_variant_rub_price(self, admin_client_logged, admin_prefix, seeded):
        moto, _ = seeded
        html = admin_client_logged.get(url(admin_prefix, f"catalog/motorcycle/{moto.pk}/change/")).content.decode()
        assert "190 000 ₽" in html and "235 000 ₽" in html

    def test_lead_change_shows_configuration(self, admin_client_logged, admin_prefix, seeded):
        _, lead = seeded
        html = admin_client_logged.get(url(admin_prefix, f"leads/lead/{lead.pk}/change/")).content.decode()
        assert "<b>variant</b>: 5 kW" in html and "<b>options</b>: ABS" in html

    def test_site_settings_shows_rate_info(self, admin_client_logged, admin_prefix, seeded):
        html = admin_client_logged.get(url(admin_prefix, "catalog/sitesettings/1/change/")).content.decode()
        assert "90.0000 ₽ за $ (cbr_xml, на 07.11.2026)" in html

    def test_site_settings_rate_info_stale(self, admin_client_logged, admin_prefix, clock):
        SiteSettings.load()
        html =admin_client_logged.get(url(admin_prefix, "catalog/sitesettings/1/change/")).content.decode()
        assert "нет данных" in html and "УСТАРЕЛ" in html

    def test_anonymous_redirected_to_login(self, client, admin_prefix):
        response = client.get(url(admin_prefix, "leads/lead/"))
        assert response.status_code == 302 and "login" in response["Location"]


class TestCatalogImport:
    def test_get_import_page(self, admin_client_logged, admin_prefix):
        response = admin_client_logged.get(url(admin_prefix, "catalog/motorcycle/import/"))
        assert response.status_code == 200
        assert "Проверить файл" in response.content.decode()

    def test_csv_preview_then_apply(self, admin_client_logged, admin_prefix, clock):
        make_option_def(code="abs", name="ABS")
        import_url = url(admin_prefix, "catalog/motorcycle/import/")

        preview = admin_client_logged.post(import_url, {
            "file": SimpleUploadedFile("catalog.csv", IMPORT_CSV, content_type="text/csv"),
            "update_publication": "on"})

        assert preview.status_code == 200
        html = preview.content.decode()
        assert "Новая модель" in html and "Моделей в файле: <b>1</b>" in html
        assert Motorcycle.objects.count() == 0, "предпросмотр ничего не меняет"
        assert SESSION_KEY in admin_client_logged.session

        applied = admin_client_logged.post(import_url, {"step": "apply"})

        assert applied.status_code == 302
        assert applied["Location"].endswith("catalog/motorcycle/")
        moto = Motorcycle.objects.get(slug="storm-x")
        assert moto.is_published is True
        assert [(v.label, v.price_usd) for v in moto.variants.all()] == [("5 kW", Decimal("1000.00")),
                                                                        ("8 kW", Decimal("1500.00"))]
        assert moto.options.get().status == MotorcycleOption.Status.OPTIONAL
        assert SESSION_KEY not in admin_client_logged.session

    def test_apply_without_publication_flag(self, admin_client_logged, admin_prefix, clock):
        make_option_def(code="abs")
        import_url = url(admin_prefix, "catalog/motorcycle/import/")
        admin_client_logged.post(import_url, {"file": SimpleUploadedFile("c.csv", IMPORT_CSV)})
        admin_client_logged.post(import_url, {"step": "apply"})

        assert Motorcycle.objects.get(slug="storm-x").is_published is False

    def test_reimport_shows_unchanged(self, admin_client_logged, admin_prefix, clock):
        make_option_def(code="abs")
        import_url = url(admin_prefix, "catalog/motorcycle/import/")
        admin_client_logged.post(import_url, {"file": SimpleUploadedFile("c.csv", IMPORT_CSV), "update_publication": "on"})
        admin_client_logged.post(import_url, {"step": "apply"})

        again = admin_client_logged.post(import_url, {"file": SimpleUploadedFile("c.csv", IMPORT_CSV),
                                                      "update_publication": "on"})

        assert "Без изменений" in again.content.decode()

    def test_bad_file_shows_error(self, admin_client_logged, admin_prefix):
        bad = "slug;name;variant_label;battery_ah\r\nstorm-x;Storm;V;100\r\n".encode()  # ok, но опция неизвестна
        bad = bad.replace(b"battery_ah", b"battery_ah;opt:turbo").replace(b";100", b";100;5")

        response = admin_client_logged.post(url(admin_prefix, "catalog/motorcycle/import/"),
                                            {"file": SimpleUploadedFile("c.csv", bad)}, follow=True)

        assert response.status_code == 200
        assert "Файл не принят" in response.content.decode()
        assert Motorcycle.objects.count() == 0

    def test_missing_file_rerenders_form(self, admin_client_logged, admin_prefix):
        response = admin_client_logged.post(url(admin_prefix, "catalog/motorcycle/import/"), {})
        assert response.status_code == 200
        assert "file" in response.context["form"].errors

    def test_apply_without_upload_redirects_back(self, admin_client_logged, admin_prefix):
        response = admin_client_logged.post(url(admin_prefix, "catalog/motorcycle/import/"), {"step": "apply"})
        assert response.status_code == 302 and response["Location"].endswith("catalog/motorcycle/import/")

    def test_nan_price_reports_error_instead_of_500(self, admin_client_logged, admin_prefix):
        data = "slug;name;variant_label;battery_ah;price_usd\r\nstorm-x;Storm;V;100;nan\r\n".encode()

        response = admin_client_logged.post(url(admin_prefix, "catalog/motorcycle/import/"),
                                            {"file": SimpleUploadedFile("c.csv", data)})

        assert "Файл не принят" in response.content.decode()

    def test_staff_without_permission_forbidden(self, client, admin_prefix, django_user_model):
        staff = django_user_model.objects.create_user("clerk", password="very-secret-password-123", is_staff=True)
        client.force_login(staff)

        assert client.get(url(admin_prefix, "catalog/motorcycle/import/")).status_code == 403
        assert client.get(url(admin_prefix, "catalog/motorcycle/export.xlsx")).status_code == 403

    def test_export_xlsx(self, admin_client_logged, admin_prefix, seeded):
        response = admin_client_logged.get(url(admin_prefix, "catalog/motorcycle/export.xlsx"))

        assert response.status_code == 200
        assert "ivax-catalog.xlsx" in response["Content-Disposition"]
        sheet = load_workbook(io.BytesIO(response.content))["Каталог"]
        assert sheet.max_row == 3  # заголовок + 2 варианта


class TestActions:
    def _action(self, client, prefix, model_url, action, ids):
        return client.post(url(prefix, model_url), {"action": action, "_selected_action": [str(i) for i in ids]})

    def test_lead_export_csv_with_formula_guard(self, admin_client_logged, admin_prefix, clock):
        lead = make_lead(name="=HYPERLINK(\"http://evil\")", message="@SUM(A1)", total_rub=None,
                         config={"variant": "-V", "options": ["A", "B"], "color": "+Red"})

        response = self._action(admin_client_logged, admin_prefix, "leads/lead/", "export_csv", [lead.pk])

        assert response.status_code == 200
        assert response["Content-Type"].startswith("text/csv")
        text = response.content.decode("utf-8")
        assert text.startswith("﻿")
        rows = list(csv.reader(io.StringIO(text.lstrip("﻿")), delimiter=";"))
        assert rows[0][0] == "№"
        row = rows[1]
        assert row[1] == "07.11.2026 12:00"
        assert row[4] == "'=HYPERLINK(\"http://evil\")"
        assert row[5] == "'+79123456789"
        assert row[7] == "'-V" and row[8] == "A, B" and row[9] == "'+Red"
        assert row[10] == "" and row[11] == "'@SUM(A1)"

    def test_lead_anonymize_action(self, admin_client_logged, admin_prefix, clock):
        lead = make_lead()
        make_outbox(lead=lead, body="Иван +79123456789")

        admin_client_logged.post(url(admin_prefix, "leads/lead/"), {
            "action": "anonymize", "_selected_action": [str(lead.pk)], "confirm": "yes"})

        lead.refresh_from_db()
        assert lead.name == "—" and lead.notifications.get().body == "[обезличено]"

    @pytest.mark.parametrize("action, status", [("mark_in_progress", Lead.Status.IN_PROGRESS),
                                                ("mark_done", Lead.Status.DONE)])
    def test_lead_status_actions(self, admin_client_logged, admin_prefix, clock, action, status):
        lead = make_lead()
        self._action(admin_client_logged, admin_prefix, "leads/lead/", action, [lead.pk])
        lead.refresh_from_db()
        assert lead.status == status

    def test_outbox_retry_now_only_requeues(self, admin_client_logged, admin_prefix, rsps, clock):
        from datetime import timedelta

        dead = make_outbox(status=Outbox.Status.DEAD, attempts=8, next_attempt_at=clock.current - timedelta(days=1))
        waiting = make_outbox(attempts=2, next_attempt_at=clock.current + timedelta(hours=1))
        sent = make_outbox(status=Outbox.Status.SENT, next_attempt_at=clock.current - timedelta(days=1))

        response = self._action(admin_client_logged, admin_prefix, "leads/outbox/", "retry_now",
                                [dead.pk, waiting.pk, sent.pk])

        assert response.status_code == 302
        assert len(rsps.calls) == 0, "отправку делает только send_notifications"
        dead.refresh_from_db()
        waiting.refresh_from_db()
        sent.refresh_from_db()
        assert (dead.status, dead.attempts, dead.next_attempt_at) == (Outbox.Status.PENDING, 0, clock.current)
        assert (waiting.attempts, waiting.next_attempt_at) == (2, clock.current)
        assert sent.status == Outbox.Status.SENT and sent.next_attempt_at == clock.current - timedelta(days=1)

    def test_outbox_cannot_be_deleted(self, admin_client_logged, admin_prefix, clock):
        item = make_outbox()
        assert admin_client_logged.get(url(admin_prefix, f"leads/outbox/{item.pk}/delete/")).status_code == 403
        html = admin_client_logged.get(url(admin_prefix, "leads/outbox/")).content.decode()
        assert "delete_selected" not in html

    def test_rate_refresh_action(self, admin_client_logged, admin_prefix, rsps, clock):
        rsps.get(XML_URL, body=cbr_xml(usd_value="81,0000"))
        existing = make_rate("80.0000", effective_date=date(2026, 11, 6))

        response = self._action(admin_client_logged, admin_prefix, "rates/rate/", "refresh_now", [existing.pk])

        assert response.status_code == 302
        assert Rate.objects.filter(value=Decimal("81.0000"), accepted=True).exists()

    def test_review_approve_reject(self, admin_client_logged, admin_prefix, clock):
        first = make_review(status=Review.Status.PENDING, ip_hash="a" * 64)
        second = make_review(status=Review.Status.PENDING, ip_hash="b" * 64)

        self._action(admin_client_logged, admin_prefix, "reviews/review/", "approve", [first.pk])
        self._action(admin_client_logged, admin_prefix, "reviews/review/", "reject", [second.pk])

        first.refresh_from_db()
        second.refresh_from_db()
        assert first.status == Review.Status.APPROVED and first.moderated_at == clock.current
        assert second.status == Review.Status.REJECTED
        assert first.ip_hash == "" and second.ip_hash == "", "после модерации хэш IP не храним"

    def test_publish_unpublish(self, admin_client_logged, admin_prefix, clock):
        moto = make_motorcycle(is_published=False)
        self._action(admin_client_logged, admin_prefix, "catalog/motorcycle/", "publish", [moto.pk])
        moto.refresh_from_db()
        assert moto.is_published is True
        self._action(admin_client_logged, admin_prefix, "catalog/motorcycle/", "unpublish", [moto.pk])
        moto.refresh_from_db()
        assert moto.is_published is False

    def test_duplicate_action_copies_everything_unpublished(self, admin_client_logged, admin_prefix, clock):
        moto = make_full_motorcycle(name="Storm X")

        self._action(admin_client_logged, admin_prefix, "catalog/motorcycle/", "duplicate", [moto.pk])

        clone = Motorcycle.objects.get(slug=f"{moto.slug}-copy")
        assert clone.name == "Storm X (копия)" and clone.is_published is False
        assert sorted(clone.variants.values_list("label", flat=True)) == sorted(
            moto.variants.values_list("label", flat=True))
        assert clone.options.count() == 2 and clone.colors.count() == 1

    def test_copy_same_model_twice(self, clock):
        moto = make_full_motorcycle()

        copy_motorcycle(moto)
        second = copy_motorcycle(moto)

        assert second.slug != f"{moto.slug}-copy"

    def test_rate_admin_is_read_only(self, admin_client_logged, admin_prefix):
        assert admin_client_logged.get(url(admin_prefix, "rates/rate/add/")).status_code == 403

    def test_site_settings_cannot_be_added_twice_or_deleted(self, admin_client_logged, admin_prefix):
        SiteSettings.load()
        assert admin_client_logged.get(url(admin_prefix, "catalog/sitesettings/add/")).status_code == 403
        assert admin_client_logged.get(url(admin_prefix, "catalog/sitesettings/1/delete/")).status_code == 403


class TestCsvSafe:
    @pytest.mark.parametrize("value, expected", [
        ("=1+1", "'=1+1"), ("+7900", "'+7900"), ("-5", "'-5"), ("@x", "'@x"), ("\tx", "'\tx"), ("\rx", "'\rx"),
        ("Иван", "Иван"), ("", ""), (None, ""), (123, "123"), ("a=b", "a=b"),
    ])
    def test_formula_prefixes_neutralised(self, value, expected):
        assert csv_safe(value) == expected


class TestActionPermissions:
    def _staff(self, django_user_model, *codenames):
        from django.contrib.auth.models import Permission

        user = django_user_model.objects.create_user("clerk", password="very-secret-password-123", is_staff=True)
        user.user_permissions.set(Permission.objects.filter(codename__in=codenames))
        return django_user_model.objects.get(pk=user.pk)  # сброс кэша прав

    def _actions(self, user):
        from django.contrib import admin as dj_admin
        from django.test import RequestFactory

        request = RequestFactory().get("/")
        request.user = user
        return set(dj_admin.site._registry[Lead].get_actions(request))

    def test_view_only_staff_sees_no_export_or_anonymize(self, client, admin_prefix, django_user_model, clock):
        user = self._staff(django_user_model, "view_lead")
        make_lead()
        client.force_login(user)

        response = client.get(url(admin_prefix, "leads/lead/"))

        assert response.status_code == 200
        html = response.content.decode()
        assert "export_csv" not in html and "anonymize" not in html
        assert not {"export_csv", "anonymize", "mark_done"} & self._actions(user)

    def test_view_only_staff_cannot_post_export_action(self, client, admin_prefix, django_user_model, clock):
        user = self._staff(django_user_model, "view_lead")
        lead = make_lead()
        client.force_login(user)

        response = client.post(url(admin_prefix, "leads/lead/"),
                               {"action": "export_csv", "_selected_action": [str(lead.pk)]})

        assert not response.get("Content-Type", "").startswith("text/csv")

    def test_change_and_delete_without_export_permission(self, django_user_model):
        user = self._staff(django_user_model, "view_lead", "change_lead", "delete_lead")
        actions = self._actions(user)
        assert {"anonymize", "mark_done", "mark_in_progress"} <= actions
        assert "export_csv" not in actions

    def test_export_permission_enables_csv(self, django_user_model):
        user = self._staff(django_user_model, "view_lead", "export_lead")
        assert "export_csv" in self._actions(user)

    def test_superuser_has_all_actions(self, superuser):
        assert {"export_csv", "anonymize", "mark_done", "mark_in_progress"} <= self._actions(superuser)
