"""Валидация заявки: имя (любой алфавит), телефон, подписанная метка времени, антиспам без потери заявки."""
import pytest
from django import forms as dj_forms
from django.core import signing

from apps.leads import forms as lead_forms
from apps.leads.forms import LeadForm, issue_form_token, looks_automated, normalize_phone, valid_person_name
from apps.leads.models import Lead
from tests.factories import make_full_motorcycle, make_motorcycle

pytestmark = pytest.mark.django_db


def form_data(**overrides) -> dict:
    """Валидная заявка с действующей подписанной меткой (LEAD_MIN_FILL_SECONDS=0 в тестовых настройках)."""
    return {"kind": "callback", "name": "Иван Петров", "phone": "+7 (912) 345-67-89", "consent": "on",
            "form_token": issue_form_token(), **overrides}


class FakeTime:
    """Подменяет time.time() только внутри apps.leads.forms."""

    def __init__(self, monkeypatch, start: float = 1_800_000_000.0):
        self.now = start
        monkeypatch.setattr(lead_forms.time, "time", lambda: self.now)


@pytest.fixture
def fake_time(monkeypatch):
    return FakeTime(monkeypatch)


class TestValidPersonName:
    @pytest.mark.parametrize("name", ["Ян", "Иван Петров", "John O'Neil", "Анна-Мария", "Jean-Luc", "Ёжик",
                                      "Әлфия", "Гөлназ", "Үзәк", "Җәүдәт", "Миңнулла", "Һади", "D’Artagnan",
                                      "J. R. Smith", "Zoë", "Łukasz"])
    def test_accepts_letters_of_any_alphabet(self, name):
        assert valid_person_name(name, 80) is True

    @pytest.mark.parametrize("name", ["", "Я", "1van", "-Иван", ".Ян", "Иван!", "Иван_Петров", "<script>",
                                      "Иван2", "Ив@н", "Иван\tПетров"])
    def test_rejects_non_letters(self, name):
        assert valid_person_name(name, 80) is False

    def test_max_len_boundary(self):
        assert valid_person_name("а" * 40, 40) is True
        assert valid_person_name("а" * 41, 40) is False


class TestNormalizePhone:
    @pytest.mark.parametrize("raw", ["+7 (912) 345-67-89", "8 912 345 67 89", "89123456789", "79123456789",
                                     "9123456789", "(912) 345-67-89", "  +7-912-345-6789  "])
    def test_russian_mobile_formats(self, raw):
        assert normalize_phone(raw) == "+79123456789"

    @pytest.mark.parametrize("raw, expected", [("+7 (495) 123-45-67", "+74951234567"),
                                               ("8 (8555) 12-34-56", "+78555123456"),
                                               ("4951234567", "+74951234567")])
    def test_landlines_allowed(self, raw, expected):
        assert normalize_phone(raw) == expected

    @pytest.mark.parametrize("raw, expected", [("+380 91 234 5678", "+380912345678"),
                                               ("+1 912 345 67 89", "+19123456789"),
                                               ("+998 90 123 45 67", "+998901234567"),
                                               ("+49 1512 3456 7890", "+49151234567890"),
                                               ("123456789012345", "+123456789012345")])
    def test_foreign_numbers_11_to_15_digits(self, raw, expected):
        assert normalize_phone(raw) == expected

    @pytest.mark.parametrize("raw", ["12345", "", None, "912345678", "1234567890123456", "телефон"])
    def test_rejects_wrong_length(self, raw):
        with pytest.raises(dj_forms.ValidationError):
            normalize_phone(raw)


class TestFormToken:
    def test_fresh_token_is_automated(self, fake_time, settings):
        settings.LEAD_MIN_FILL_SECONDS = 3
        token = issue_form_token()
        fake_time.now += 1
        assert looks_automated(token) is True

    def test_token_after_threshold_is_human(self, fake_time, settings):
        settings.LEAD_MIN_FILL_SECONDS = 3
        token = issue_form_token()
        fake_time.now += 3
        assert looks_automated(token) is False

    @pytest.mark.parametrize("token", ["", None])
    def test_missing_token_is_automated(self, token):
        assert looks_automated(token) is True

    @pytest.mark.parametrize("token", ["garbage", "1800000000:forged-signature", "a:b:c"])
    def test_forged_token_is_automated(self, token):
        assert looks_automated(token) is True

    def test_token_signed_with_other_salt_is_automated(self):
        assert looks_automated(signing.TimestampSigner(salt="other").sign("1")) is True

    def test_tampered_value_is_automated(self, fake_time):
        value, rest = issue_form_token().split(":", 1)
        assert looks_automated(f"{int(value) - 100}:{rest}") is True

    def test_signed_non_numeric_value_is_automated(self):
        token = signing.TimestampSigner(salt=lead_forms.TOKEN_SALT).sign("not-a-number")
        assert looks_automated(token) is True

    def test_token_older_than_a_week_is_not_spam(self, fake_time, settings):
        settings.LEAD_MIN_FILL_SECONDS = 10 ** 9
        token = issue_form_token()
        fake_time.now += 8 * 86400
        assert looks_automated(token) is False

    def test_zero_threshold_accepts_immediate_submit(self, fake_time, settings):
        settings.LEAD_MIN_FILL_SECONDS = 0
        assert looks_automated(issue_form_token()) is False

    def test_client_clock_is_irrelevant(self, fake_time, settings):
        """Метку выдаёт сервер — часы посетителя не участвуют (раньше спешащие часы давали «спам»)."""
        settings.LEAD_MIN_FILL_SECONDS = 3
        token = issue_form_token()
        fake_time.now += 60
        form = LeadForm(form_data(form_token=token))
        assert form.is_valid() and form.cleaned_data["is_spam"] is False


class TestLeadForm:
    def test_valid_callback(self):
        form = LeadForm(form_data())

        assert form.is_valid(), form.errors
        data = form.cleaned_data
        assert data["phone"] == "+79123456789"
        assert data["name"] == "Иван Петров"
        assert data["is_spam"] is False
        assert data["kind"] == Lead.Kind.CALLBACK
        assert data["motorcycle"] is None

    def test_started_at_field_removed(self):
        assert "started_at" not in LeadForm.base_fields
        assert "form_token" in LeadForm.base_fields

    def test_kind_defaults_to_callback(self):
        data = form_data()
        del data["kind"]
        form = LeadForm(data)
        assert form.is_valid()
        assert form.cleaned_data["kind"] == Lead.Kind.CALLBACK

    def test_tatar_name_accepted(self):
        form = LeadForm(form_data(name="Әлфия Җәүдәтова"))
        assert form.is_valid(), form.errors

    def test_name_whitespace_collapsed(self):
        form = LeadForm(form_data(name="  Анна   Мария  "))
        assert form.is_valid()
        assert form.cleaned_data["name"] == "Анна Мария"

    @pytest.mark.parametrize("name", ["Ё", "1van", "<script>", "Иван!"])
    def test_bad_names_rejected(self, name):
        form = LeadForm(form_data(name=name))
        assert not form.is_valid()
        assert "name" in form.errors

    def test_consent_required(self):
        data = form_data()
        del data["consent"]
        form = LeadForm(data)
        assert not form.is_valid()
        assert "согласия" in form.errors["consent"][0]

    def test_landline_phone_accepted(self):
        form = LeadForm(form_data(phone="+7 (495) 123-45-67"))
        assert form.is_valid()
        assert form.cleaned_data["phone"] == "+74951234567"

    def test_short_phone_error_on_field(self):
        form = LeadForm(form_data(phone="12-34"))
        assert not form.is_valid()
        assert "phone" in form.errors

    def test_honeypot_keeps_form_valid_but_flags_spam(self):
        form = LeadForm(form_data(website="http://spam.example"))
        assert form.is_valid()
        assert form.cleaned_data["is_spam"] is True

    def test_too_fast_submit_flags_spam(self, fake_time, settings):
        settings.LEAD_MIN_FILL_SECONDS = 30
        token = issue_form_token()
        fake_time.now += 2

        form = LeadForm(form_data(form_token=token))

        assert form.is_valid()
        assert form.cleaned_data["is_spam"] is True

    def test_slow_enough_submit_not_spam(self, fake_time, settings):
        settings.LEAD_MIN_FILL_SECONDS = 3
        token = issue_form_token()
        fake_time.now += 60

        form = LeadForm(form_data(form_token=token))

        assert form.is_valid() and form.cleaned_data["is_spam"] is False

    def test_invalid_token_flags_spam(self):
        form = LeadForm(form_data(form_token="broken"))
        assert form.is_valid() and form.cleaned_data["is_spam"] is True

    def test_missing_token_flags_spam_but_keeps_lead_valid(self):
        data = form_data()
        del data["form_token"]
        form = LeadForm(data)
        assert form.is_valid() and form.cleaned_data["is_spam"] is True

    @pytest.mark.parametrize("slug", ["Шторм", "bad slug", "a/b", "<x>"])
    def test_invalid_model_slug_is_form_error(self, slug):
        form = LeadForm(form_data(model=slug))
        assert not form.is_valid()
        assert "model" in form.errors

    def test_color_only_format_checked(self):
        for code, expected in [("purple", "purple"), ("other", "other"), ("Red!", ""), ("x", ""),
                               ("../etc", "")]:
            form = LeadForm(form_data(color=code))
            assert form.is_valid()
            assert form.cleaned_data["color"] == expected, code

    def test_published_model_sets_kind_model(self):
        moto = make_full_motorcycle()

        form = LeadForm(form_data(model=moto.slug.upper()))

        assert form.is_valid(), form.errors
        assert form.cleaned_data["motorcycle"] == moto
        assert form.cleaned_data["model"] == moto.slug
        assert form.cleaned_data["kind"] == Lead.Kind.MODEL

    def test_unpublished_model_is_not_an_error(self):
        moto = make_motorcycle(is_published=False)

        form = LeadForm(form_data(model=moto.slug))

        assert form.is_valid(), form.errors
        assert form.cleaned_data["motorcycle"] is None
        assert form.cleaned_data["kind"] == Lead.Kind.MODEL
        assert form.cleaned_data["model"] == moto.slug

    def test_unknown_model_is_not_an_error(self):
        form = LeadForm(form_data(model="no-such-bike"))
        assert form.is_valid()
        assert form.cleaned_data["motorcycle"] is None
        assert form.cleaned_data["kind"] == Lead.Kind.MODEL

    def test_kind_model_without_slug_is_accepted(self):
        form = LeadForm(form_data(kind="model"))
        assert form.is_valid()
        assert form.cleaned_data["kind"] == Lead.Kind.MODEL
        assert form.cleaned_data["motorcycle"] is None

    def test_unknown_kind_rejected(self):
        assert "kind" in LeadForm(form_data(kind="vip")).errors

    def test_options_parsed_and_deduplicated(self):
        form = LeadForm(form_data(options="abs, usb,abs,,"))
        assert form.is_valid()
        assert form.cleaned_data["options"] == ("abs", "usb")

    def test_bad_option_codes_silently_dropped(self):
        form = LeadForm(form_data(options="ABS,a,abs;drop table,../x,usb"))
        assert form.is_valid()
        assert form.cleaned_data["options"] == ("usb",)

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
