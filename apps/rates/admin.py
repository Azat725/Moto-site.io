from django.contrib import admin, messages

from .models import Rate
from .services import refresh_rate


@admin.register(Rate)
class RateAdmin(admin.ModelAdmin):
    list_display = ("effective_date", "currency", "value", "source", "accepted", "note", "fetched_at")
    list_filter = ("accepted", "source")
    readonly_fields = ("currency", "value", "effective_date", "source", "fetched_at", "accepted", "note")
    actions = ["refresh_now"]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    @admin.action(description="Обновить курс с сайта ЦБ РФ сейчас")
    def refresh_now(self, request, queryset):
        result = refresh_rate()
        self.message_user(request, result.message, messages.SUCCESS if result.ok else messages.ERROR)
