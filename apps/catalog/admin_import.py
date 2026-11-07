"""Страница админки «Импорт из Excel/CSV»: загрузка → предпросмотр изменений → применение."""
from __future__ import annotations

import json

from django import forms
from django.contrib import messages
from django.http import HttpResponse
from django.shortcuts import redirect
from django.template.response import TemplateResponse
from django.views import View

from . import catalog_io, spreadsheet
from .models import OptionDef

SESSION_KEY = "catalog_import_models"


class UploadForm(forms.Form):
    file = forms.FileField(label="Файл Excel (.xlsx) или CSV")
    update_publication = forms.BooleanField(
        label="Обновить статус публикации из файла", required=False, initial=False
    )


def _parse(upload) -> list[dict]:
    codes = set(OptionDef.objects.values_list("code", flat=True))
    rows = spreadsheet.read_table(upload.read())
    return [catalog_io.normalize_model(raw, codes) for raw in spreadsheet.rows_to_models(rows)]


def _to_session(models: list[dict]) -> str:
    return json.dumps(models, default=str)


def _from_session(payload: str) -> list[dict]:
    from decimal import Decimal

    models = json.loads(payload)
    for model in models:
        model["variants"] = tuple(
            {**v, "price_usd": None if v.get("price_usd") in (None, "None") else Decimal(v["price_usd"])}
            for v in model["variants"]
        )
        model["features"] = tuple(model["features"])
    return models


class CatalogImportView(View):
    admin_site = None
    template = "admin/catalog/import.html"

    def _render(self, request, **context):
        base = self.admin_site.each_context(request) | {"title": "Импорт каталога из Excel / CSV"}
        return TemplateResponse(request, self.template, base | context)

    def get(self, request):
        return self._render(request, form=UploadForm())

    def post(self, request):
        if request.POST.get("step") == "apply":
            return self._apply(request)
        form = UploadForm(request.POST, request.FILES)
        if not form.is_valid():
            return self._render(request, form=form)
        try:
            models = _parse(form.cleaned_data["file"])
        except (catalog_io.CatalogError, ValueError, KeyError) as exc:
            messages.error(request, f"Файл не принят: {exc}")
            return self._render(request, form=form)
        request.session[SESSION_KEY] = _to_session(models)
        request.session[SESSION_KEY + ":pub"] = form.cleaned_data["update_publication"]
        return self._render(request, report=catalog_io.compare(models), count=len(models))

    def _apply(self, request):
        payload = request.session.pop(SESSION_KEY, None)
        if not payload:
            messages.error(request, "Сначала загрузите файл.")
            return redirect("admin:catalog_motorcycle_import")
        count = catalog_io.apply(_from_session(payload), request.session.pop(SESSION_KEY + ":pub", False))
        messages.success(request, f"Импорт выполнен: обработано моделей — {count}.")
        return redirect("admin:catalog_motorcycle_changelist")


def export_catalog_xlsx(request):
    options = list(OptionDef.objects.values_list("code", "name"))
    data = spreadsheet.build_workbook(catalog_io.export_models(), options)
    response = HttpResponse(data, content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    response["Content-Disposition"] = 'attachment; filename="ivax-catalog.xlsx"'
    return response
