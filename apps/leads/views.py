from django.conf import settings
from django.http import HttpResponseRedirect, JsonResponse
from django.urls import reverse
from django.views.decorators.http import require_POST

from .forms import LeadForm
from .ratelimit import client_ip, hit
from .services import create_lead, hash_ip


def _wants_json(request) -> bool:
    return "application/json" in request.headers.get("Accept", "")


def _error(request, status: int, message: str, fields: dict | None = None):
    if _wants_json(request):
        return JsonResponse({"success": False, "error": message, "fields": fields or {}}, status=status)
    return HttpResponseRedirect(reverse("pages:thanks") + "?error=1")


@require_POST
def create(request):
    """Приём заявки. Уведомления отправляет отдельный процесс send_notifications (очередь Outbox)."""
    if settings.SITE_MODE != "live":
        return _error(request, 403, "Демо-версия сайта: заявки не принимаются.")
    form = LeadForm(request.POST)
    if not form.is_valid():
        fields = {k: [str(e) for e in v] for k, v in form.errors.items() if k != "__all__"}
        return _error(request, 400, "Проверьте поля формы.", fields)

    ip = client_ip(request)
    limit, window = settings.LEAD_RATE_LIMIT
    if not hit(f"lead:{hash_ip(ip)}", limit, window):
        return _error(request, 429, "Слишком много заявок. Попробуйте позже или позвоните нам.")

    lead = create_lead(form.cleaned_data, ip)
    client_total = form.cleaned_data.get("client_total")
    data = {"id": lead.pk, "total_rub": lead.total_rub,
            "price_changed": bool(client_total and lead.total_rub and client_total != lead.total_rub)}
    if _wants_json(request):
        return JsonResponse({"success": True, "data": data}, status=201)
    return HttpResponseRedirect(reverse("pages:thanks"))
