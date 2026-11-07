import csv

from django.contrib import admin, messages
from django.http import HttpResponse
from django.utils import timezone
from django.utils.html import format_html_join

from .models import Lead, Outbox
from .notifiers import deliver

FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


def csv_safe(value) -> str:
    text = "" if value is None else str(value)
    return "'" + text if text.startswith(FORMULA_PREFIXES) else text


class OutboxInline(admin.TabularInline):
    model = Outbox
    extra = 0
    fields = ("channel", "status", "attempts", "last_error", "sent_at")
    readonly_fields = fields
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Lead)
class LeadAdmin(admin.ModelAdmin):
    list_display = ("id", "created_at", "status", "kind", "name", "phone", "model_name", "total_rub")
    list_filter = ("status", "kind", "created_at")
    list_editable = ("status",)
    search_fields = ("name", "phone", "model_name", "message")
    date_hierarchy = "created_at"
    readonly_fields = ("created_at", "kind", "name", "phone", "contact_way", "message", "model_name",
                       "configuration", "total_rub", "consent_at", "consent_version", "page", "anonymized_at")
    fields = ("status", "manager_note", *readonly_fields)
    inlines = [OutboxInline]
    actions = ["mark_in_progress", "mark_done", "export_csv", "anonymize"]

    def has_add_permission(self, request):
        return False

    @admin.display(description="Конфигурация")
    def configuration(self, obj):
        cfg = obj.config or {}
        rows = [(k, v if not isinstance(v, list) else ", ".join(v)) for k, v in cfg.items() if v not in ("", None, [])]
        return format_html_join("\n", "<div><b>{}</b>: {}</div>", rows) or "—"

    @admin.action(description="Отметить «В работе»")
    def mark_in_progress(self, request, queryset):
        queryset.update(status=Lead.Status.IN_PROGRESS)

    @admin.action(description="Отметить «Завершена»")
    def mark_done(self, request, queryset):
        queryset.update(status=Lead.Status.DONE)

    @admin.action(description="Обезличить (удалить персональные данные)")
    def anonymize(self, request, queryset):
        count = queryset.update(name="—", phone="—", message="", ip_hash="", anonymized_at=timezone.now())
        self.message_user(request, f"Обезличено заявок: {count}", messages.SUCCESS)

    @admin.action(description="Выгрузить в CSV (Excel)")
    def export_csv(self, request, queryset):
        response = HttpResponse(content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = 'attachment; filename="leads.csv"'
        response.write("﻿")
        writer = csv.writer(response, delimiter=";")
        writer.writerow(["№", "Дата", "Статус", "Тип", "Имя", "Телефон", "Модель", "Комплектация", "Опции", "Цвет",
                         "Итого, ₽", "Комментарий"])
        for lead in queryset:
            cfg = lead.config or {}
            writer.writerow([csv_safe(v) for v in (
                lead.pk, timezone.localtime(lead.created_at).strftime("%d.%m.%Y %H:%M"), lead.get_status_display(),
                lead.get_kind_display(), lead.name, lead.phone, lead.model_name, cfg.get("variant", ""),
                ", ".join(cfg.get("options", [])), cfg.get("color", ""), lead.total_rub or "", lead.message,
            )])
        return response


@admin.register(Outbox)
class OutboxAdmin(admin.ModelAdmin):
    list_display = ("created_at", "channel", "subject", "status", "attempts", "next_attempt_at", "last_error")
    list_filter = ("status", "channel")
    readonly_fields = ("channel", "subject", "body", "lead", "status", "attempts", "next_attempt_at", "last_error",
                       "created_at", "sent_at")
    actions = ["retry_now"]

    def has_add_permission(self, request):
        return False

    @admin.action(description="Повторить отправку сейчас")
    def retry_now(self, request, queryset):
        items = list(queryset.exclude(status=Outbox.Status.SENT))
        for item in items:
            item.status = Outbox.Status.PENDING
        ok = sum(deliver(item) for item in items)
        self.message_user(request, f"Отправлено: {ok} из {len(items)}", messages.INFO)
