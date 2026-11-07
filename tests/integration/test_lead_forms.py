"""Валидация заявки: телефон, имя, антиспам, цвет, модель."""
import time

import pytest
from django import forms as dj_forms

from apps.leads.forms import LeadForm, normalize_phone
from apps.leads.models import Lead
from tests.factories import make_color, make_full_motorcycle, make_motorcycle

pytestmark = pytest.mark.django_db


def form_data(**overrides) -> dict:
    return {"kind": "callback", "name": "Иван Петров", "phone": "+7 (912) 345-67-89", "consent": "on", **overrides}


class TestNormalizePhone:
    @pytest.mark.parametrize("raw", ["+7 (912) 345-67-89", "8 912 345 67 89", "89123456789", "79123456789",
                                     "9123456789", "(912) 345-67-89", "  +7-912-345-6789  "])
    def test_valid_mobile_formats(self, raw):
        assert normalize_phone(raw) == "+79123456789"

    @pytest.mark.parametrize("raw", ["+7 (495) 123-45-67", "84951234567", "4951234567", "12345", "",
                                     "+1 912 345 67 89", "+7 912 345 67 899", "+380 91 234 5678", None])
    def test_rejects_non_mobile_or_wrong_length(self, raw):
        with pytest.raises(dj_forms.ValidationError):
            normalize_phone(raw)


class TestLeadForm:
    def test_valid_callback(self):
        form = LeadForm(form_data())

        assert form.is_valid(), form.errors
        assert form.cleaned_data["phone"] == "+79123456789"
        assert form.cleaned_data["name"] == "Иван Петров"
        assert form.is_spam is False

    def test_name_whitespace_collapsed(self):
        form = LeadForm(form_data(name="  Анна   Мария  "))
        assert form.is_valid()
        assert form.cleaned_data["name"] == "Анна Мария"

    @pytest.mark.parametrize("name", ["Ё", "1van", "<script>", "Иван!", "Иван_Петров", "-Иван"])
    def test_bad_names_rejected(self, name):
        form = LeadForm(form_data(name=name))
        assert not form.is_valid()
        assert "name" in form.errors

    @pytest.mark.parametrize("name", ["Ян", "John O'Neil", "Анна-Мария", "Jean-Luc", "Ёжик"])
    def test_good_names_accepted(self, name):
        assert LeadForm(form_data(name=name)).is_valid()

    def test_consent_required(self):
        data = form_data()
        del data["consent"]
        form = LeadForm(data)
        assert not form.is_valid()
        assert "согласия" in form.errors["consent"][0]

    def test_bad_phone_error_on_field(self):
        form = LeadForm(form_data(phone="+7 495 123 45 67"))
        assert not form.is_valid()
        assert "phone" in form.errors

    def test_honeypot_marks_spam(self):
        form = LeadForm(form_data(website="http://spam.example"))
        assert not form.is_valid()
        assert form.is_spam is True

    def test_too_fast_submit_is_spam(self, settings):
        settings.LEAD_MIN_FILL_SECONDS = 30
        started = int((time.time() - 2) * 1000)

        form = LeadForm(form_data(started_at=started))

        assert not form.is_valid()
        assert form.is_spam is True

    def test_slow_enough_submit_passes(self, settings):
        settings.LEAD_MIN_FILL_SECONDS = 3
        started = int((time.time() - 60) * 1000)

        assert LeadForm(form_data(started_at=started)).is_valid()

    def test_missing_started_at_is_not_spam(self, settings):
        settings.LEAD_MIN_FILL_SECONDS = 3
        assert LeadForm(form_data()).is_valid()

    @pytest.mark.xfail(reason="BUG: forms.py:81 compares client-side Date.now() with server time; a visitor whose "
                              "clock is ahead of the server is treated as spam and the lead is silently dropped",
                       strict=True)
    def test_client_clock_ahead_is_not_spam(self, settings):
        settings.LEAD_MIN_FILL_SECONDS = 3
        started = int((time.time() + 120) * 1000)  # часы клиента спешат на 2 минуты, форму заполняли минуту

        form = LeadForm(form_data(started_at=started))

        assert form.is_spam is False

    def test_regular_errors_are_not_spam(self):
        form = LeadForm(form_data(name="", phone=""))
        assert not form.is_valid()
        assert form.is_spam is False

    def test_unknown_color_rejected(self):
        form = LeadForm(form_data(color="purple"))
        assert not form.is_valid()
        assert form.errors["color"] == ["Неизвестный цвет."]

    def test_known_and_other_color_accepted(self):
        make_color(code="red")
        assert LeadForm(form_data(color="red")).is_valid()
        assert LeadForm(form_data(color="other")).is_valid()

    def test_published_model_sets_kind_model(self):
        moto = make_full_motorcycle()

        form = LeadForm(form_data(model=moto.slug))

        assert form.is_valid(), form.errors
        assert form.cleaned_data["motorcycle"] == moto
        assert form.cleaned_data["kind"] == Lead.Kind.MODEL

    def test_unpublished_model_rejected(self):
        moto = make_motorcycle(is_published=False)
        form = LeadForm(form_data(model=moto.slug))
        assert not form.is_valid()
        assert "Модель не найдена." in form.errors["model"]

    def test_unknown_model_rejected(self):
        assert "model" in LeadForm(form_data(model="no-such-bike")).errors

    def test_kind_model_without_model_rejected(self):
        form = LeadForm(form_data(kind="model"))
        assert not form.is_valid()
        assert "Не выбрана модель." in form.errors["model"]

    def test_options_parsed_and_deduplicated(self):
        form = LeadForm(form_data(options="abs, usb,abs,,"))
        assert form.is_valid()
        assert form.cleaned_data["options"] == ("abs", "usb")

    @pytest.mark.parametrize("options", ["ABS", "a", "abs;drop table", "../x"])
    def test_bad_option_codes_rejected(self, options):
        assert "options" in LeadForm(form_data(options=options)).errors

    @pytest.mark.parametrize("page, expected", [("/moto/storm/", "/moto/storm/"), ("https://evil.example/", ""),
                                                ("javascript:alert(1)", ""), ("", "")])
    def test_page_only_relative_paths(self, page, expected):
        form = LeadForm(form_data(page=page))
        assert form.is_valid()
        assert form.cleaned_data["page"] == expected

    def test_message_stripped(self):
        form = LeadForm(form_data(message="  перезвоните вечером  "))
        assert form.is_valid()
        assert form.cleaned_data["message"] == "перезвоните вечером"

    @pytest.mark.parametrize("total", ["-1", "100000001"])
    def test_client_total_bounds(self, total):
        assert "client_total" in LeadForm(form_data(client_total=total)).errors
