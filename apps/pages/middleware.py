"""Защита публичных адресов от больших тел запросов и загрузок файлов (до разбора формы и CSRF)."""
from django.conf import settings
from django.http import HttpResponse

PUBLIC_BODY_LIMIT = 64 * 1024


class PublicUploadGuardMiddleware:
    """Публичные формы шлют только короткий текст. Файлы и большие тела разрешены лишь в админке."""

    def __init__(self, get_response):
        self.get_response = get_response
        self.admin_prefix = "/" + settings.ADMIN_PATH

    def __call__(self, request):
        if request.method in ("POST", "PUT", "PATCH") and not request.path_info.startswith(self.admin_prefix):
            if request.content_type == "multipart/form-data":
                return HttpResponse("Загрузка файлов здесь не поддерживается.", status=415)
            try:
                length = int(request.META.get("CONTENT_LENGTH") or 0)
            except ValueError:
                length = PUBLIC_BODY_LIMIT + 1
            if length > PUBLIC_BODY_LIMIT:
                return HttpResponse("Слишком большой запрос.", status=413)
        return self.get_response(request)
