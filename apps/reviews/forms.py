import re

from django import forms

from apps.catalog.models import Motorcycle

NAME_RE = re.compile(r"^[A-Za-zА-Яа-яЁё][A-Za-zА-Яа-яЁё \-'’.]{1,39}$")


class ReviewForm(forms.Form):
    display_name = forms.CharField(max_length=40)
    city = forms.CharField(max_length=40, required=False)
    rating = forms.IntegerField(min_value=1, max_value=5)
    text = forms.CharField(min_length=20, max_length=1000)
    model = forms.SlugField(max_length=60, required=False)
    consent = forms.BooleanField(error_messages={"required": "Нужно согласие на обработку персональных данных."})
    publication_consent = forms.BooleanField(
        error_messages={"required": "Нужно согласие на публикацию имени и города вместе с отзывом."}
    )
    website = forms.CharField(required=False)

    def clean_display_name(self) -> str:
        name = " ".join(self.cleaned_data["display_name"].split())
        if not NAME_RE.match(name):
            raise forms.ValidationError("Имя — буквами, от 2 символов.")
        return name

    def clean_city(self) -> str:
        city = " ".join((self.cleaned_data.get("city") or "").split())
        if city and not NAME_RE.match(city):
            raise forms.ValidationError("Название города — буквами.")
        return city

    def clean_text(self) -> str:
        return self.cleaned_data["text"].strip()

    def clean(self):
        data = super().clean()
        if data.get("website"):
            raise forms.ValidationError("spam", code="spam")
        slug = data.get("model")
        data["motorcycle"] = Motorcycle.objects.filter(slug=slug, is_published=True).first() if slug else None
        return data
