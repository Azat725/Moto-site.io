"""Настройки для pytest."""
from .base import *  # noqa: F401,F403
from .base import BASE_DIR

DEBUG = False
SECRET_KEY = "test-secret-key-not-for-production-0123456789"
DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}}
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
MEDIA_ROOT = BASE_DIR / "data" / "test-media"
LEAD_MIN_FILL_SECONDS = 0
TELEGRAM = {
    "BOT_TOKEN": "123:test",
    "CHAT_ID": "42",
    "API_BASE": "https://tg.test",
    "INCLUDE_PD": False,
    "TIMEOUT": 2,
}
LEAD_NOTIFY_EMAILS = ["manager@example.com"]
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}
