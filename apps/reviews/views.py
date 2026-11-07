from django.conf import settings
from django.http import HttpResponseRedirect, JsonResponse
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.leads.ratelimit import client_ip, limit_key, over_limit
from apps.leads.services import hash_ip

from .forms import ReviewForm
from .models import Review


def _respond(request, status: int, payload: dict):
    if "application/json" in request.headers.get("Accept", ""):
        return JsonResponse(payload, status=status)
    suffix = "?sent=1" if payload.get("success") else "?error=1"
    return HttpResponseRedirect(reverse("pages:reviews") + suffix)


@require_POST
def submit(request):
    if settings.SITE_MODE != "live":
        return _respond(request, 403, {"success": False, "error": "Демо-версия сайта: отзывы не принимаются."})
    ip_hash = hash_ip(limit_key(client_ip(request)))
    form = ReviewForm(request.POST)
    if not form.is_valid():
        if any(e.code == "spam" for e in form.non_field_errors().as_data()):
            return _respond(request, 200, {"success": True})
        fields = {k: [str(e) for e in v] for k, v in form.errors.items() if k != "__all__"}
        return _respond(request, 400, {"success": False, "error": "Проверьте поля формы.", "fields": fields})
    limit, window = settings.REVIEW_RATE_LIMIT
    if over_limit(Review.objects.filter(ip_hash=ip_hash), limit, window):
        return _respond(request, 429, {"success": False, "error": "Слишком много отзывов с одного адреса."})
    data = form.cleaned_data
    now = timezone.now()
    Review.objects.create(
        display_name=data["display_name"], city=data["city"], rating=data["rating"], text=data["text"],
        motorcycle=data["motorcycle"], consent_at=now, publication_consent_at=now, ip_hash=ip_hash,
    )
    return _respond(request, 201, {"success": True})
