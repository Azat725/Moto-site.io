"""Продакшен (VPS в РФ за Caddy/nginx с TLS). Все секреты — только из окружения."""
from django.core.exceptions import ImproperlyConfigured

from .base import *  # noqa: F401,F403
from .base import SECRET_KEY, env, env_bool, env_int

if not SECRET_KEY or SECRET_KEY.startswith("dev-only") or len(SECRET_KEY) < 50:
    raise ImproperlyConfigured("Задайте DJANGO_SECRET_KEY (не короче 50 символов) в окружении.")
if env("IP_HASH_SALT", "dev-salt") == "dev-salt":
    raise ImproperlyConfigured("Задайте IP_HASH_SALT в окружении.")
if env("ADMIN_PATH", "manage-ivax/").strip("/") in ("manage-ivax", "admin", ""):
    raise ImproperlyConfigured("Задайте свой ADMIN_PATH (случайная строка), стандартный путь админки публичен.")

DEBUG = False
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = env_bool("SECURE_SSL_REDIRECT", True)
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_HSTS_SECONDS = env_int("SECURE_HSTS_SECONDS", 31536000)
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = False
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}
# Preload-список HSTS включим после выбора постоянного домена (необратимо надолго).
SILENCED_SYSTEM_CHECKS = ["security.W021"]
