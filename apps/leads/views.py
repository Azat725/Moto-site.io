import logging
import threading

from django.conf import settings
from django.db import close_old_connections, transaction
from django.http import HttpResponseRedirect, JsonResponse
from django.urls import reverse
from django.views.decorators.http import require_POST

from . import notifiers
from .forms import LeadForm
from .ratelimit import client_ip, hit
from .services import create_lead, hash_ip

logger = logging.getLogger(__name__)


def _wants_json(request) -> bool:
    return "application/json" in request.headers.get("Accept", "")


def _deliver_in_background(lead_id: int) -> None:
    def run():
        try:
            for item in notifiers.Outbox.objects.filter(lead_id=lead_id, status="pending"):
                notifiers.deliver(item)
        except Exception:  # фоновая попытка; повтор сделает send_notifications
            logger.exception("Фоновая отправка уведомлений по заявке %s не удалась", lead_id)
        finally:
            close_old_connections()

    threading.Thread(target=run, daemon=True).start()


def _error(request, status: int, message: str, fields: dict | None = None):
    if _wants_json(request):
        return JsonResponse({"success": False, "error": message, "fields": fields or {}}, status=status)
    return HttpResponseRedirect(reverse("pages:thanks") + "?error=1")


@require_POST
def create(request):
    ip = client_ip(request)
    limit, window = settings.LEAD_RATE_LIMIT
    if not hit(f"lead:{hash_ip(ip)}", limit, window):
        return _error(request, 429, "Слишком много заявок. Попробуйте позже или позвоните нам.")

    form = LeadForm(request.POST)
    if not form.is_valid():
        if form.is_spam:
            return JsonResponse({"success": True, "data": {"id": None}}) if _wants_json(request) else \
                HttpResponseRedirect(reverse("pages:thanks"))
        fields = {k: [str(e) for e in v] for k, v in form.errors.items() if k != "__all__"}
        return _error(request, 400, "Проверьте поля формы.", fields)

    try:
        lead = create_lead(form.cleaned_data, ip)
    except ValueError as exc:
        return _error(request, 400, str(exc))
    if settings.SITE_MODE == "live":
        transaction.on_commit(lambda: _deliver_in_background(lead.pk))

    client_total = form.cleaned_data.get("client_total")
    data = {"id": lead.pk, "total_rub": lead.total_rub,
            "price_changed": bool(client_total and lead.total_rub and client_total != lead.total_rub)}
    if _wants_json(request):
        return JsonResponse({"success": True, "data": data}, status=201)
    return HttpResponseRedirect(reverse("pages:thanks"))
