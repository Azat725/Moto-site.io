from contextvars import ContextVar

from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.urls import path
from django.utils.html import format_html

from . import pricing
from .admin_import import CatalogImportView, export_catalog_xlsx
from .admin_forms import SiteSettingsForm
from .admin_permissions import DUPLICATE_PERMISSIONS, EXPORT_PERMISSIONS, IMPORT_PERMISSIONS
from .models import Color, Motorcycle, MotorcycleOption, OptionDef, Photo, SiteSettings, Variant
from .services import current_context


PRICE_CTX: ContextVar = ContextVar("price_ctx", default=None)


def _rub(value: int | None) -> str:
    return "по запросу" if value is None else f"{value:,}".replace(",", " ") + " ₽"


class VariantInline(admin.StackedInline):
    model = Variant
    extra = 0
    fields = ("label", ("battery_ah", "price_usd", "price_rub"), ("voltage_v", "motor_power_w"),
              ("drive", "sort_order"), ("top_speed_kmh", "range_max_km"), ("brakes", "tyre_rear"))
    readonly_fields = ("price_rub",)

    @admin.display(description="Цена на сайте")
    def price_rub(self, obj):
        if not obj.pk:
            return "—"
        ctx = current_context()
        kop = pricing.variant_kopecks(obj.price_usd, ctx)
        return _rub(None if kop is None else pricing.ceil_to_step(kop, ctx.step))


class OptionInline(admin.StackedInline):
    model = MotorcycleOption
    extra = 0
    fields = ("option", "status", "price_usd")
    autocomplete_fields = ("option",)


class PhotoInline(admin.TabularInline):
    model = Photo
    extra = 0
    fields = ("preview", "image", "alt", "sort_order")
    readonly_fields = ("preview",)

    @admin.display(description="Превью")
    def preview(self, obj):
        return format_html('<img src="{}" alt="{}" style="height:60px">', obj.image.url, obj.alt) if obj.pk and obj.image else "—"


@admin.register(Motorcycle)
class MotorcycleAdmin(admin.ModelAdmin):
    change_list_template = "admin/catalog/motorcycle/change_list.html"
    list_display = ("name", "type", "line", "power", "price_from", "is_published", "is_popular", "sort_order")
    list_editable = ("is_published", "is_popular", "sort_order")
    list_filter = ("is_published", "type", "line", "cooling")
    search_fields = ("name", "slug", "supplier_ref")
    prepopulated_fields = {"slug": ("name",)}
    filter_horizontal = ("colors",)
    inlines = [VariantInline, OptionInline, PhotoInline]
    actions = ["publish", "unpublish", "duplicate"]
    list_per_page = 25
    ordering = ("sort_order", "name", "pk")
    fieldsets = (
        ("Основное", {"fields": ("name", "slug", "line", "type", "is_published", "is_popular", "sort_order",
                                 "short", "description", "features", "colors")}),
        ("Характеристики (по умолчанию для всех вариантов)", {"fields": (
            ("motor_power_w", "motor_layout", "drive", "cooling"), ("voltage_v", "battery_type"),
            ("top_speed_kmh", "range_min_km", "range_max_km"), "brakes", ("suspension_front", "suspension_rear"),
            ("tyre_front", "tyre_rear", "tyre_kind"))}),
        ("Служебное", {"classes": ("collapse",), "fields": ("origin_country", "supplier_ref")}),
    )

    def get_urls(self):
        def guarded(view, permissions):
            def wrapper(request, *args, **kwargs):
                if not request.user.has_perms(permissions):
                    raise PermissionDenied
                return view(request, *args, **kwargs)
            return self.admin_site.admin_view(wrapper)

        custom = [
            path("import/", guarded(CatalogImportView.as_view(admin_site=self.admin_site), IMPORT_PERMISSIONS),
                 name="catalog_motorcycle_import"),
            path("export.xlsx", guarded(export_catalog_xlsx, EXPORT_PERMISSIONS), name="catalog_motorcycle_export"),
        ]
        return custom + super().get_urls()

    def get_queryset(self, request):
        return super().get_queryset(request).prefetch_related("variants")

    def changelist_view(self, request, extra_context=None):
        token = PRICE_CTX.set(current_context())  # один расчёт курса на страницу списка
        try:
            context = {"can_import": request.user.has_perms(IMPORT_PERMISSIONS),
                       "can_export": request.user.has_perms(EXPORT_PERMISSIONS)}
            return super().changelist_view(request, context | (extra_context or {}))
        finally:
            PRICE_CTX.reset(token)

    @admin.display(description="Мощность")
    def power(self, obj):
        return f"{obj.power_kw} кВт"

    @admin.display(description="Цена от")
    def price_from(self, obj):
        ctx = PRICE_CTX.get() or current_context()
        prices = [pricing.ceil_to_step(k, ctx.step) for v in obj.variants.all()
                  if (k := pricing.variant_kopecks(v.price_usd, ctx)) is not None]
        return _rub(min(prices, default=None))

    @admin.action(description="Опубликовать", permissions=["change"])
    def publish(self, request, queryset):
        queryset.update(is_published=True)

    @admin.action(description="Снять с публикации", permissions=["change"])
    def unpublish(self, request, queryset):
        queryset.update(is_published=False)

    def has_duplicate_permission(self, request):
        return request.user.has_perms(DUPLICATE_PERMISSIONS)

    @admin.action(description="Создать копию (неопубликованную)", permissions=["duplicate"])
    def duplicate(self, request, queryset):
        for moto in queryset:
            with transaction.atomic():
                copy_motorcycle(moto)
        self.message_user(request, "Копии созданы — отредактируйте название и адрес.", messages.SUCCESS)


@transaction.atomic
def copy_motorcycle(moto: Motorcycle) -> Motorcycle:
    variants, options, colors = list(moto.variants.all()), list(moto.options.all()), list(moto.colors.all())
    clone = Motorcycle.objects.get(pk=moto.pk)
    clone.pk = None
    suffix, number = "-copy", 1
    while Motorcycle.objects.filter(slug=moto.slug[:60 - len(suffix)].rstrip("-") + suffix).exists():
        number += 1
        suffix = f"-copy-{number}"
    clone.slug = moto.slug[:60 - len(suffix)].rstrip("-") + suffix
    clone.name = f"{moto.name} (копия)"[:60]
    clone.is_published = False
    clone.save()
    clone.colors.set(colors)
    Variant.objects.bulk_create([Variant(**{**_fields(v), "motorcycle": clone}) for v in variants])
    MotorcycleOption.objects.bulk_create(
        [MotorcycleOption(motorcycle=clone, option_id=o.option_id, status=o.status, price_usd=o.price_usd) for o in options]
    )
    return clone


def _fields(obj) -> dict:
    return {f.name: getattr(obj, f.name) for f in obj._meta.concrete_fields if f.name not in ("id", "motorcycle")}


@admin.register(OptionDef)
class OptionDefAdmin(admin.ModelAdmin):
    list_display = ("name", "code", "sort_order")
    search_fields = ("name", "code")
    ordering = ("sort_order", "name", "pk")
    list_per_page = 50


@admin.register(Color)
class ColorAdmin(admin.ModelAdmin):
    list_display = ("name", "swatch", "code", "sort_order")
    search_fields = ("name", "code")
    ordering = ("sort_order", "name", "pk")
    list_per_page = 50

    @admin.display(description="Цвет")
    def swatch(self, obj):
        return format_html('<span style="display:inline-block;width:24px;height:24px;border-radius:50%;'
                           'background:{};border:1px solid #999"></span>', obj.hex)


@admin.register(SiteSettings)
class SiteSettingsAdmin(admin.ModelAdmin):
    form = SiteSettingsForm
    readonly_fields = ("current_rate_info",)
    fieldsets = (
        ("Цены", {"fields": ("markup_rub", "rounding_step", "rate_mode", "manual_rate", "current_rate_info")}),
        ("Контакты и реквизиты", {"fields": ("phone", "email", "address", "hours", "legal_name", "inn", "ogrn")}),
        ("Соцсети", {"fields": ("telegram_url", "vk_url", "whatsapp_url")}),
    )

    @admin.display(description="Курс сейчас")
    def current_rate_info(self, obj):
        from apps.rates.services import current_rate

        rate = current_rate()
        date = rate.effective_date.strftime("%d.%m.%Y") if rate.effective_date else "нет данных"
        stale = " — УСТАРЕЛ, проверьте обновление курса" if rate.is_stale else ""
        return f"{rate.value} ₽ за $ ({rate.source}, на {date}){stale}"

    def has_add_permission(self, request):
        return super().has_add_permission(request) and not SiteSettings.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False
