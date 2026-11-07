from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models


class Review(models.Model):
    """Отзыв покупателя. На сайте показываются только одобренные администратором."""

    class Status(models.TextChoices):
        PENDING = "pending", "На модерации"
        APPROVED = "approved", "Опубликован"
        REJECTED = "rejected", "Отклонён"

    created_at = models.DateTimeField("Получен", auto_now_add=True)
    display_name = models.CharField("Имя", max_length=40)
    city = models.CharField("Город", max_length=40, blank=True)
    rating = models.PositiveSmallIntegerField("Оценка", validators=[MinValueValidator(1), MaxValueValidator(5)])
    text = models.TextField("Текст", max_length=1000)
    motorcycle = models.ForeignKey(
        "catalog.Motorcycle", verbose_name="Модель", on_delete=models.SET_NULL, null=True, blank=True
    )
    status = models.CharField("Статус", max_length=10, choices=Status.choices, default=Status.PENDING, db_index=True)
    consent_at = models.DateTimeField("Согласие на обработку ПДн")
    publication_consent_at = models.DateTimeField("Согласие на публикацию имени и города")
    ip_hash = models.CharField(max_length=64, blank=True, editable=False)
    moderated_at = models.DateTimeField("Проверен", null=True, blank=True)

    class Meta:
        verbose_name = "Отзыв"
        verbose_name_plural = "Отзывы"
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.display_name}: {self.rating}★"
