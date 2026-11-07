"""Базовые настройки IV&AX MOTO. Секреты и всё, что зависит от окружения, берутся из env / .env."""
from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from pathlib import Path

from django.utils.csp import CSP

from config.env import env, env_bool, env_int, env_list, load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent.parent
load_dotenv(BASE_DIR / ".env")

SECRET_KEY = env("DJANGO_SECRET_KEY", "dev-only-insecure-key-do-not-use-in-production")
DEBUG = env_bool("DJANGO_DEBUG", False)
ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS", ["localhost", "127.0.0.1", "testserver"])
CSRF_TRUSTED_ORIGINS = env_list("DJANGO_CSRF_TRUSTED_ORIGINS", [])

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.sitemaps",
    "axes",
    "apps.catalog",
    "apps.rates",
    "apps.leads",
    "apps.reviews",
    "apps.pages",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "django.middleware.csp.ContentSecurityPolicyMiddleware",
    "axes.middleware.AxesMiddleware",
]

AUTHENTICATION_BACKENDS = [
    "axes.backends.AxesStandaloneBackend",
    "django.contrib.auth.backends.ModelBackend",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.template.context_processors.csp",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "apps.pages.context_processors.site",
            ],
        },
    },
]

DATA_DIR = Path(env("DATA_DIR", str(BASE_DIR / "data")))
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": DATA_DIR / "db.sqlite3",
        "OPTIONS": {"timeout": 20, "init_command": "PRAGMA journal_mode=WAL;"},
    }
}
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 12}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]
PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.ScryptPasswordHasher",
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
]

LANGUAGE_CODE = "ru"
TIME_ZONE = "Europe/Moscow"
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_URL = "/media/"
MEDIA_ROOT = Path(env("MEDIA_ROOT", str(BASE_DIR / "media")))
FILE_UPLOAD_MAX_MEMORY_SIZE = 5 * 1024 * 1024
DATA_UPLOAD_MAX_MEMORY_SIZE = 12 * 1024 * 1024

CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache", "LOCATION": "ivax"}}

# --- Безопасность (усиливается в prod.py) ---
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_AGE = 12 * 60 * 60
CSRF_COOKIE_SAMESITE = "Lax"
X_FRAME_OPTIONS = "DENY"
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "strict-origin-when-cross-origin"
SECURE_CSP = {
    "default-src": [CSP.SELF],
    "script-src": [CSP.SELF, CSP.NONCE],
    "style-src": [CSP.SELF, CSP.UNSAFE_INLINE],
    "img-src": [CSP.SELF, "data:"],
    "font-src": [CSP.SELF],
    "connect-src": [CSP.SELF],
    "frame-ancestors": [CSP.NONE],
    "base-uri": [CSP.SELF],
    "form-action": [CSP.SELF],
    "object-src": [CSP.NONE],
}

AXES_FAILURE_LIMIT = 5
AXES_COOLOFF_TIME = timedelta(minutes=15)
AXES_LOCKOUT_PARAMETERS = [["username", "ip_address"]]
AXES_RESET_ON_SUCCESS = True

# --- Сайт ---
ADMIN_PATH = env("ADMIN_PATH", "manage-ivax/").strip("/") + "/"
SITE_MODE = env("SITE_MODE", "live")  # live — работающий сервер; demo — статическое демо без отправки форм
SITE_DOMAIN = env("SITE_DOMAIN", "https://ivax-moto.ru").rstrip("/")
SITE_NOINDEX = env_bool("SITE_NOINDEX", True)  # пока сайт не запущен на своём домене — закрыт от поисковиков
SHOW_SAMPLE_REVIEWS = env_bool("SHOW_SAMPLE_REVIEWS", False)

# --- Курс валют ---
RATES = {
    "CURRENCY": "USD",
    "SOURCES": env_list("RATE_SOURCES", ["cbr_xml", "cbr_json"]),
    "CBR_XML_URL": env("CBR_XML_URL", "https://www.cbr.ru/scripts/XML_daily.asp"),
    "CBR_JSON_URL": env("CBR_JSON_URL", "https://www.cbr-xml-daily.ru/daily_json.js"),
    "TIMEOUT": 8,
    "MIN": Decimal(env("RATE_MIN", "20")),
    "MAX": Decimal(env("RATE_MAX", "500")),
    "MAX_JUMP_PCT": Decimal(env("RATE_MAX_JUMP_PCT", "20")),
    "FALLBACK": Decimal(env("FALLBACK_USD_RATE", "80.0000")),
    "STALE_DAYS": 3,
}

# --- Заявки и уведомления ---
IP_HASH_SALT = env("IP_HASH_SALT", "dev-salt")
LEAD_RATE_LIMIT = (env_int("LEAD_RATE_LIMIT_COUNT", 5), env_int("LEAD_RATE_LIMIT_SECONDS", 600))
REVIEW_RATE_LIMIT = (env_int("REVIEW_RATE_LIMIT_COUNT", 3), env_int("REVIEW_RATE_LIMIT_SECONDS", 86400))
LEAD_MIN_FILL_SECONDS = env_int("LEAD_MIN_FILL_SECONDS", 3)
LEAD_RETENTION_DAYS = env_int("LEAD_RETENTION_DAYS", 1095)
CONSENT_VERSION = env("CONSENT_VERSION", "2026-11-07")

TELEGRAM = {
    "BOT_TOKEN": env("TELEGRAM_BOT_TOKEN"),
    "CHAT_ID": env("TELEGRAM_CHAT_ID"),
    "API_BASE": env("TELEGRAM_API_BASE", "https://api.telegram.org").rstrip("/"),
    "INCLUDE_PD": env_bool("TELEGRAM_INCLUDE_PD", False),
    "TIMEOUT": 10,
}
LEAD_NOTIFY_EMAILS = env_list("LEAD_NOTIFY_EMAILS", [])
EMAIL_BACKEND = env("EMAIL_BACKEND", "django.core.mail.backends.smtp.EmailBackend")
EMAIL_HOST = env("EMAIL_HOST", "")
EMAIL_PORT = env_int("EMAIL_PORT", 465)
EMAIL_HOST_USER = env("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = env("EMAIL_HOST_PASSWORD", "")
EMAIL_USE_SSL = env_bool("EMAIL_USE_SSL", True)
EMAIL_USE_TLS = env_bool("EMAIL_USE_TLS", False)
EMAIL_TIMEOUT = 15
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", "IV&AX MOTO <noreply@ivax-moto.ru>")
OUTBOX_BACKOFF_SECONDS = [60, 300, 1800, 7200, 21600, 43200, 86400]
OUTBOX_MAX_ATTEMPTS = 8

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "root": {"handlers": ["console"], "level": env("LOG_LEVEL", "INFO")},
}

# --- Оформление ---
SITE_LOGO = env("SITE_LOGO", "volt")  # volt | horns | fang (сравнение: /preview/logo/)
