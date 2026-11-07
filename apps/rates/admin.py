from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect
from django.urls import path
from django.utils.decorators import method_decorator
from django.views.decorators.http import require_POST

from .models import Rate
from .services import refresh_rate


@admin.register(Rate)
class RateAdmin(admin.ModelAdmin):
    change_list_template = "admin/rates/rate/change_list.html"
    list_display = ("effective_date", "currency", "value", "source", "accepted", "note", "fetched_at")
    list_filter = ("accepted", "source")
    search_fields = ("currency", "source", "note")
    ordering = ("-fetched_at", "-pk")
    date_hierarchy = "effective_date"
    list_per_page = 50
    readonly_fields = ("currency", "value", "effective_date", "source", "fetched_at", "accepted", "note")
    actions = ["refresh_now"]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def has_refresh_permission(self, request):
        return request.user.has_perm("rates.change_rate")

    def get_urls(self):
        return [path("refresh/", self.admin_site.admin_view(self.refresh_view),
                     name="rates_rate_refresh")] + super().get_urls()

    def changelist_view(self, request, extra_context=None):
        context = {"can_refresh": self.has_refresh_permission(request)} | (extra_context or {})
        return super().changelist_view(request, context)

    @method_decorator(require_POST)
    def refresh_view(self, request):
        if not self.has_refresh_permission(request):
            raise PermissionDenied
        self.refresh_now(request, self.get_queryset(request))
        return redirect("admin:rates_rate_changelist")

    @admin.action(description="Обновить курс с сайта ЦБ РФ сейчас", permissions=["refresh"])
    def refresh_now(self, request, queryset):
        result = refresh_rate()
        self.message_user(request, result.message, messages.SUCCESS if result.ok else messages.ERROR)
