from django.db import models


class Rate(models.Model):
    """Полученный курс валюты. Используется последний принятый (accepted=True)."""

    currency = models.CharField("Валюта", max_length=3, default="USD")
    value = models.DecimalField("Курс, ₽", max_digits=12, decimal_places=4)
    effective_date = models.DateField("Дата курса ЦБ")
    source = models.CharField("Источник", max_length=40)
    fetched_at = models.DateTimeField("Получен", auto_now_add=True)
    accepted = models.BooleanField("Принят", default=True)
    note = models.CharField("Комментарий", max_length=250, blank=True)

    class Meta:
        verbose_name = "Курс валюты"
        verbose_name_plural = "Курсы валют"
        ordering = ["-fetched_at"]
        indexes = [models.Index(fields=["currency", "accepted", "-fetched_at"])]

    def __str__(self) -> str:
        return f"{self.currency} {self.value} на {self.effective_date:%d.%m.%Y}"
