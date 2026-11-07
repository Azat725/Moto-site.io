"""Права сотрудников, неизменяемые данные и подтверждение опасных операций."""
from datetime import timedelta

import pytest
from django.contrib import admin
from django.contrib.auth.models import Permission
from django.test import Client, RequestFactory
from django.urls import reverse

from apps.catalog.models import Motorcycle, MotorcycleOption, OptionDef, SiteSettings
from apps.leads.models import Lead, Outbox
from apps.rates.models import Rate
from apps.reviews.models import Review
from tests.factories import make_lead, make_motorcycle, make_outbox, make_rate, make_review

pytestmark = pytest.mark.django_db


def staff(django_user_model, *permissions):
    user = django_user_model.objects.create_user("operator", is_staff=True)
    user.user_permissions.set(Permission.objects.filter(codename__in=permissions))
    return user


def action(client, model, name, ids, **extra):
    opts = model._meta
    return client.post(reverse(f"admin:{opts.app_label}_{opts.model_name}_changelist"), {
        "action": name, "_selected_action": [str(pk) for pk in ids], **extra,
    })


@pytest.mark.parametrize("flags", [{"is_staff": False}, {"is_staff": True, "is_active": False}])
def test_non_staff_and_inactive_users_cannot_login(client, django_user_model, flags):
    django_user_model.objects.create_user("blocked", password="long-test-password", **flags)
    response = client.post(reverse("admin:login"), {"username": "blocked", "password": "long-test-password"})
    assert response.status_code == 200
    assert "_auth_user_id" not in client.session


def test_csrf_is_required_for_admin_mutations(superuser):
    client = Client(enforce_csrf_checks=True)
    client.force_login(superuser)
    response = client.post(reverse("admin:catalog_color_add"), {"name": "Красный"})
    assert response.status_code == 403
    assert client.post(reverse("admin:rates_rate_refresh")).status_code == 403


def test_site_settings_add_respects_model_permissions(django_user_model):
    user = staff(django_user_model, "view_sitesettings")
    request = RequestFactory().get("/")
    request.user = user
    assert not admin.site._registry[SiteSettings].has_add_permission(request)


def test_rate_viewer_cannot_refresh_or_delete(client, django_user_model, clock, rsps):
    client.force_login(staff(django_user_model, "view_rate", "delete_rate"))
    rate = make_rate()
    action(client, Rate, "refresh_now", [rate.pk])
    assert not rsps.calls
    assert client.get(reverse("admin:rates_rate_delete", args=[rate.pk])).status_code == 403


def test_motorcycle_only_editor_cannot_import_or_clone_related_data(client, django_user_model, clock):
    client.force_login(staff(django_user_model, "view_motorcycle", "change_motorcycle", "add_motorcycle"))
    moto = make_motorcycle()
    response = client.get(reverse("admin:catalog_motorcycle_import"))
    assert response.status_code == 403
    action(client, Motorcycle, "duplicate", [moto.pk])
    assert Motorcycle.objects.count() == 1
    assert client.get(reverse("admin:catalog_motorcycle_export")).status_code == 403


def test_anonymize_requires_explicit_confirmation(admin_client_logged, clock):
    lead = make_lead()
    response = action(admin_client_logged, Lead, "anonymize", [lead.pk])
    assert response.status_code == 200
    assert "Подтвердить обезличивание" in response.content.decode()
    lead.refresh_from_db()
    assert lead.name == "Иван"
    response = action(admin_client_logged, Lead, "anonymize", [lead.pk], confirm="yes")
    assert response.status_code == 302
    lead.refresh_from_db()
    assert lead.name == "—" and lead.anonymized_at == clock.current


def test_retry_does_not_touch_sending_and_reports_actual_count(admin_client_logged, clock):
    sending = make_outbox(status=Outbox.Status.SENDING, locked_until=clock.current + timedelta(seconds=60))
    sent = make_outbox(status=Outbox.Status.SENT)
    dead = make_outbox(status=Outbox.Status.DEAD, attempts=8)
    response = action(admin_client_logged, Outbox, "retry_now", [sending.pk, sent.pk, dead.pk])
    sending.refresh_from_db()
    assert sending.status == Outbox.Status.SENDING
    dead.refresh_from_db()
    assert dead.status == Outbox.Status.PENDING and dead.attempts == 0
    from django.contrib.messages import get_messages
    assert any("Поставлено в очередь: 1." in str(msg) for msg in get_messages(response.wsgi_request))


def test_reviews_cannot_be_fabricated_in_admin(admin_client_logged):
    assert admin_client_logged.get(reverse("admin:reviews_review_add")).status_code == 403


def test_review_form_moderation_preserves_original_and_consent(admin_client_logged, clock):
    review = make_review(status=Review.Status.PENDING, ip_hash="a" * 64)
    review.refresh_from_db()
    original_consent = review.consent_at
    response = admin_client_logged.post(reverse("admin:reviews_review_change", args=[review.pk]), {
        "status": Review.Status.APPROVED, "display_name": "Подмена", "text": "Чужой текст",
        "consent_at_0": "2000-01-01", "_save": "Сохранить",
    })
    assert response.status_code == 302
    review.refresh_from_db()
    assert review.status == Review.Status.APPROVED
    assert review.moderated_at == clock.current and review.ip_hash == ""
    assert review.display_name == "Анна" and review.consent_at == original_consent


def test_manual_rate_requires_value(admin_client_logged):
    site = SiteSettings.load()
    data = {f.name: getattr(site, f.name) for f in site._meta.fields if f.editable}
    data.update(rate_mode=SiteSettings.RateMode.MANUAL, manual_rate="", _save="Сохранить")
    response = admin_client_logged.post(reverse("admin:catalog_sitesettings_change", args=[site.pk]), data)
    assert response.status_code == 200
    assert "manual_rate" in response.context["adminform"].form.errors


def test_lead_post_cannot_change_customer_data_or_price(admin_client_logged, clock):
    lead = make_lead(total_rub=190000)
    response = admin_client_logged.post(reverse("admin:leads_lead_change", args=[lead.pk]), {
        "status": Lead.Status.DONE, "manager_note": "Обработано", "name": "Подмена", "total_rub": "1",
        "notifications-TOTAL_FORMS": "0", "notifications-INITIAL_FORMS": "0", "_save": "Сохранить",
    })
    assert response.status_code == 302
    lead.refresh_from_db()
    assert (lead.status, lead.manager_note) == (Lead.Status.DONE, "Обработано")
    assert lead.name == "Иван" and lead.total_rub == 190000


def motorcycle_data(moto):
    data = {f.name: getattr(moto, f.name) for f in moto._meta.fields if f.editable}
    for prefix in ("variants", "options", "photos"):
        data.update({f"{prefix}-TOTAL_FORMS": "0", f"{prefix}-INITIAL_FORMS": "0"})
    data["_save"] = "Сохранить"
    return data


def test_invalid_option_inline_rolls_back_parent_edit(admin_client_logged, clock):
    moto = make_motorcycle(name="Исходное название")
    option = OptionDef.objects.create(code="abs", name="ABS")
    data = motorcycle_data(moto) | {
        "name": "Новое название", "options-TOTAL_FORMS": "1", "options-0-option": str(option.pk),
        "options-0-status": MotorcycleOption.Status.OPTIONAL, "options-0-price_usd": "",
    }
    response = admin_client_logged.post(reverse("admin:catalog_motorcycle_change", args=[moto.pk]), data)
    assert response.status_code == 200
    inline = next(i for i in response.context["inline_admin_formsets"] if i.formset.prefix == "options")
    assert "price_usd" in inline.formset.errors[0]
    moto.refresh_from_db()
    assert moto.name == "Исходное название" and not moto.options.exists()


def test_referenced_option_delete_is_protected(admin_client_logged, clock):
    from tests.factories import make_motorcycle_option

    link = make_motorcycle_option(make_motorcycle())
    response = admin_client_logged.post(reverse("admin:catalog_optiondef_delete", args=[link.option_id]), {"post": "yes"})
    assert response.status_code == 200
    assert OptionDef.objects.filter(pk=link.option_id).exists()
    assert MotorcycleOption.objects.filter(pk=link.pk).exists()


def test_long_slug_can_be_copied_repeatedly(clock):
    from apps.catalog.admin import copy_motorcycle

    moto = make_motorcycle(slug="m" * 60)
    first, second = copy_motorcycle(moto), copy_motorcycle(moto)
    assert first.slug != second.slug
    assert len(first.slug) <= 60 and len(second.slug) <= 60
    first.full_clean()
    second.full_clean()


def test_catalog_import_permissions_can_be_granted_to_staff(client, django_user_model, clock):
    from apps.catalog.admin_permissions import IMPORT_PERMISSIONS

    user = staff(django_user_model, *(p.split(".")[1] for p in IMPORT_PERMISSIONS))
    client.force_login(user)
    assert client.get(reverse("admin:catalog_motorcycle_import")).status_code == 200


def test_view_only_staff_cannot_moderate_review(client, django_user_model, clock):
    client.force_login(staff(django_user_model, "view_review"))
    review = make_review(status=Review.Status.PENDING)
    action(client, Review, "approve", [review.pk])
    review.refresh_from_db()
    assert review.status == Review.Status.PENDING


def test_refresh_rate_without_existing_history(admin_client_logged, clock, rsps):
    from tests.fixtures.cbr import XML_URL, cbr_xml

    endpoint = reverse("admin:rates_rate_refresh")
    assert admin_client_logged.get(endpoint).status_code == 405
    rsps.get(XML_URL, body=cbr_xml())
    assert admin_client_logged.post(endpoint).status_code == 302
    assert Rate.objects.filter(accepted=True).count() == 1


def test_rate_refresh_button_checks_permission(client, django_user_model, rsps):
    client.force_login(staff(django_user_model, "view_rate"))
    response = client.post(reverse("admin:rates_rate_refresh"))
    assert response.status_code == 403 and not rsps.calls
