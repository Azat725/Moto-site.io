"""Единый переход статуса отзыва при индивидуальной и массовой модерации."""
from django.utils import timezone

from .models import Review


def moderation_fields(status: str) -> dict:
    if status not in Review.Status.values:
        raise ValueError("Неизвестный статус отзыва.")
    fields = {"status": status, "moderated_at": None}
    if status != Review.Status.PENDING:
        fields.update(moderated_at=timezone.now(), ip_hash="")
    return fields


def moderate_reviews(queryset, status: str) -> int:
    return queryset.exclude(status=status).update(**moderation_fields(status))
