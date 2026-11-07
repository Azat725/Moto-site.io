"""Валидация заявок. Принцип: заявку с контактами не теряем — сомнительные данные сохраняем с пометкой."""
from __future__ import annotations

import re
import time

from django import forms
from django.conf import settings
from django.core import signing

from apps.catalog.models import Motorcycle

from .models import Lead

OPTION_CODE_RE = re.compile(r"^[a-z0-9_]{2,40}$")
NAME_EXTRA = set(" -'’.")
TOKEN_SALT = "ivax.lead-form"


def valid_person_name(value: str, max_len: int) -> bool:
    """Буквы любого алфавита (включая татарские Ә Ө Ү Җ Ң Һ), пробел, дефис, апостроф, точка."""
    return 2 <= len(value) <= max_len and value[0].isalpha() and all(ch.isalpha() or ch in NAME_EXTRA for ch in value)


def normalize_phone(raw: str) -> str:
    """Российские номера → +7XXXXXXXXXX; другие страны — +цифры (10–15 цифр)."""
    digits = re.sub(r"\D", "", raw or "")
    if len(digits) == 11 and digits[0] in "78":
        return "+7" + digits[1:]
    if len(digits) == 10:
        return "+7" + digits
    if 11 <= len(digits) <= 15:
        return "+" + digits
    raise forms.ValidationError("Укажите номер телефона полностью, например +7 (9XX) XXX-XX-XX")


def issue_form_token() -> str:
    return signing.TimestampSigner(salt=TOKEN_SALT).sign(str(int(time.time())))


def filled_too_fast(token: str) -> bool:
    """True только если подписанная метка валидна и форма заполнена быстрее порога (бот)."""
    if not token:
        return False
    try:
        issued = int(signing.TimestampSigner(salt=TOKEN_SALT).unsign(token, max_age=7 * 86400))
    except (signing.BadSignature, ValueError):
        return False
    return time.time() - issued < settings.LEAD_MIN_FILL_SECONDS


class LeadForm(forms.Form):
    kind = forms.ChoiceField(choices=Lead.Kind.choices, initial=Lead.Kind.CALLBACK, required=False)
    name = forms.CharField(max_length=80)
    phone = forms.CharField(max_length=30)
    message = forms.CharField(max_length=600, required=False)
    way = forms.ChoiceField(choices=Lead.Way.choices, required=False)
    consent = forms.BooleanField(
        required=True, error_messages={"required": "Без согласия на обработку персональных данных заявку не принять."}
    )
    model = forms.CharField(max_length=60, required=False)
    variant = forms.IntegerField(min_value=1, required=False)
    options = forms.CharField(max_length=600, required=False)
    color = forms.CharField(max_length=40, required=False)
    client_total = forms.IntegerField(min_value=0, max_value=100_000_000, required=False)
    page = forms.CharField(max_length=200, required=False)
    form_token = forms.CharField(max_length=120, required=False)
    website = forms.CharField(required=False)  # honeypot: люди это поле не видят

    def clean_name(self) -> str:
        name = " ".join(self.cleaned_data["name"].split())
        if not valid_person_name(name, 80):
            raise forms.ValidationError("Введите имя буквами (от 2 символов).")
        return name

    def clean_phone(self) -> str:
        return normalize_phone(self.cleaned_data["phone"])

    def clean_message(self) -> str:
        return self.cleaned_data.get("message", "").strip()

    def clean_options(self) -> tuple[str, ...]:
        raw = self.cleaned_data.get("options") or ""
        return tuple(dict.fromkeys(c.strip() for c in raw.split(",") if OPTION_CODE_RE.match(c.strip())))

    def clean_color(self) -> str:
        code = (self.cleaned_data.get("color") or "").strip()
        return code if OPTION_CODE_RE.match(code) or code == "other" else ""

    def clean_page(self) -> str:
        page = (self.cleaned_data.get("page") or "").strip()
        return page if page.startswith("/") else ""

    def clean(self):
        data = super().clean()
        data["is_spam"] = bool(data.get("website")) or filled_too_fast(data.get("form_token", ""))
        slug = (data.get("model") or "").strip().lower()
        data["model"] = slug
        data["motorcycle"] = Motorcycle.objects.filter(slug=slug, is_published=True).first() if slug else None
        data["kind"] = Lead.Kind.MODEL if slug else (data.get("kind") or Lead.Kind.CALLBACK)
        return data
