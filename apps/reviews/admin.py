from django.contrib import admin

from .models import Review
from .services import moderate_reviews, moderation_fields


@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    list_display = ("created_at", "display_name", "city", "rating", "motorcycle", "status")
    list_filter = ("status", "rating")
    search_fields = ("display_name", "city", "text", "motorcycle__name")
    list_select_related = ("motorcycle",)
    ordering = ("-created_at", "-pk")
    list_per_page = 25
    date_hierarchy = "created_at"
    readonly_fields = ("display_name", "city", "rating", "text", "motorcycle", "created_at", "consent_at",
                       "publication_consent_at", "moderated_at")
    fieldsets = (
        ("Модерация", {"fields": ("status", "moderated_at")}),
        ("Исходный отзыв покупателя", {"fields": ("display_name", "city", "rating", "text", "motorcycle")}),
        ("Получение и согласия", {"fields": ("created_at", "consent_at", "publication_consent_at")}),
    )
    actions = ["approve", "reject"]

    def has_add_permission(self, request):
        return False

    def save_model(self, request, obj, form, change):
        if "status" in form.changed_data:
            for field, value in moderation_fields(obj.status).items():
                setattr(obj, field, value)
        super().save_model(request, obj, form, change)

    @admin.action(description="Опубликовать", permissions=["change"])
    def approve(self, request, queryset):
        moderate_reviews(queryset, Review.Status.APPROVED)

    @admin.action(description="Отклонить", permissions=["change"])
    def reject(self, request, queryset):
        moderate_reviews(queryset, Review.Status.REJECTED)
