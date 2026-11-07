"""Продакшен (VPS в РФ за Caddy/nginx с TLS). Все секреты — только из окружения."""
import re
from urllib.parse import urlsplit

from django.core.exceptions import ImproperlyConfigured

from .base import *  # noqa: F401,F403
from .base import SECRET_KEY, env, env_bool, env_int

if not SECRET_KEY or SECRET_KEY.startswith("dev-only") or len(SECRET_KEY) < 50:
    raise ImproperlyConfigured("Задайте DJANGO_SECRET_KEY (не короче 50 символов) в окружении.")
if len(env("IP_HASH_SALT")) < 32:
    raise ImproperlyConfigured("Задайте случайный IP_HASH_SALT (не короче 32 символов) в окружении.")
admin_path = env("ADMIN_PATH").strip("/")
if (admin_path == "manage-ivax" or not re.fullmatch(r"[A-Za-z0-9_-]{12,80}", admin_path)):
    raise ImproperlyConfigured("Задайте свой ADMIN_PATH (случайная строка), стандартный путь админки публичен.")
if (not env("DJANGO_ALLOWED_HOSTS") or not ALLOWED_HOSTS
        or any(host in {"localhost", "127.0.0.1", "testserver"}
               or not re.fullmatch(r"[A-Za-z0-9]+(?:[.-][A-Za-z0-9-]+)*", host) for host in ALLOWED_HOSTS)):
    raise ImproperlyConfigured("Задайте DJANGO_ALLOWED_HOSTS: конкретные домены без схемы и масок.")
if not CSRF_TRUSTED_ORIGINS:
    raise ImproperlyConfigured("Задайте DJANGO_CSRF_TRUSTED_ORIGINS с HTTPS-адресами сайта.")
for origin in CSRF_TRUSTED_ORIGINS:
    parsed = urlsplit(origin)
    if (parsed.scheme != "https" or parsed.netloc not in ALLOWED_HOSTS
            or parsed.path or parsed.query or parsed.fragment):
        raise ImproperlyConfigured("DJANGO_CSRF_TRUSTED_ORIGINS: только HTTPS-адреса из DJANGO_ALLOWED_HOSTS.")

DEBUG = False
SHOW_SAMPLE_REVIEWS = False
SITE_MODE = "live"
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
