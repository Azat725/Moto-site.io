"""Валидация заявок. Все входные данные проверяются здесь, до записи в БД."""
from __future__ import annotations

import re
import time

from django import forms
from django.conf import settings

from apps.catalog.models import Color, Motorcycle

from .models import Lead

NAME_RE = re.compile(r"^[A-Za-zА-Яа-яЁё][A-Za-zА-Яа-яЁё \-'’.]{1,79}$")
OPTION_CODE_RE = re.compile(r"^[a-z0-9_]{2,40}$")


def normalize_phone(raw: str) -> str:
    digits = re.sub(r"\D", "", raw or "")
    if len(digits) == 11 and digits[0] in "78":
        digits = "7" + digits[1:]
    elif len(digits) == 10:
        digits = "7" + digits
    if len(digits) != 11 or not digits.startswith("79"):
        raise forms.ValidationError("Укажите мобильный телефон полностью: +7 (9XX) XXX-XX-XX")
    return f"+{digits}"


class LeadForm(forms.Form):
    kind = forms.ChoiceField(choices=Lead.Kind.choices, initial=Lead.Kind.CALLBACK)
    name = forms.CharField(max_length=80)
    phone = forms.CharField(max_length=30)
    message = forms.CharField(max_length=600, required=False)
    way = forms.ChoiceField(choices=Lead.Way.choices, required=False)
    consent = forms.BooleanField(
        required=True, error_messages={"required": "Без согласия на обработку персональных данных заявку не принять."}
    )
    model = forms.SlugField(max_length=60, required=False)
    variant = forms.IntegerField(min_value=1, required=False)
    options = forms.CharField(max_length=600, required=False)
    color = forms.CharField(max_length=40, required=False)
    client_total = forms.IntegerField(min_value=0, max_value=100_000_000, required=False)
    page = forms.CharField(max_length=200, required=False)
    started_at = forms.IntegerField(required=False)
    website = forms.CharField(required=False)  # honeypot: люди это поле не видят

    def clean_name(self) -> str:
        name = " ".join(self.cleaned_data["name"].split())
        if not NAME_RE.match(name):
            raise forms.ValidationError("Введите имя буквами (от 2 символов).")
        return name

    def clean_phone(self) -> str:
        return normalize_phone(self.cleaned_data["phone"])

    def clean_message(self) -> str:
        return self.cleaned_data.get("message", "").strip()

    def clean_options(self) -> tuple[str, ...]:
        raw = self.cleaned_data.get("options") or ""
        codes = tuple(dict.fromkeys(c.strip() for c in raw.split(",") if c.strip()))
        if any(not OPTION_CODE_RE.match(c) for c in codes):
            raise forms.ValidationError("Некорректный список опций.")
        return codes

    def clean_color(self) -> str:
        code = (self.cleaned_data.get("color") or "").strip()
        if code and code != "other" and not Color.objects.filter(code=code).exists():
            raise forms.ValidationError("Неизвестный цвет.")
        return code

    def clean_page(self) -> str:
        page = (self.cleaned_data.get("page") or "").strip()
        return page if page.startswith("/") else ""

    def clean(self):
        data = super().clean()
        if data.get("website"):
            raise forms.ValidationError("spam", code="spam")
        started = data.get("started_at")
        if started and time.time() - started / 1000 < settings.LEAD_MIN_FILL_SECONDS:
            raise forms.ValidationError("spam", code="spam")
        slug = data.get("model")
        if slug:
            moto = Motorcycle.objects.filter(slug=slug, is_published=True).first()
            if moto is None:
                self.add_error("model", "Модель не найдена.")
            data["motorcycle"] = moto
            if moto is not None:
                data["kind"] = Lead.Kind.MODEL
        if data.get("kind") == Lead.Kind.MODEL and not data.get("motorcycle"):
            self.add_error("model", "Не выбрана модель.")
        return data

    @property
    def is_spam(self) -> bool:
        return any(e.code == "spam" for e in self.non_field_errors().as_data())
