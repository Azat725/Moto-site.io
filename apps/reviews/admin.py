from django.contrib import admin
from django.utils import timezone

from .models import Review


@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    list_display = ("created_at", "display_name", "city", "rating", "motorcycle", "status")
    list_filter = ("status", "rating")
    search_fields = ("display_name", "text")
    readonly_fields = ("created_at", "consent_at", "publication_consent_at", "moderated_at")
    actions = ["approve", "reject"]

    @admin.action(description="Опубликовать", permissions=["change"])
    def approve(self, request, queryset):
        queryset.update(status=Review.Status.APPROVED, moderated_at=timezone.now(), ip_hash="")

    @admin.action(description="Отклонить", permissions=["change"])
    def reject(self, request, queryset):
        queryset.update(status=Review.Status.REJECTED, moderated_at=timezone.now(), ip_hash="")
