"""Проверки настроек, редактируемых владельцем в админке."""
from django import forms

from .models import SiteSettings


class SiteSettingsForm(forms.ModelForm):
    class Meta:
        model = SiteSettings
        fields = "__all__"

    def clean(self):
        data = super().clean()
        if data.get("rate_mode") == SiteSettings.RateMode.MANUAL and data.get("manual_rate") is None:
            self.add_error("manual_rate", "Укажите ручной курс или выберите автоматический режим.")
        return data
