"""Сборка статического демо для GitHub Pages (manage.py export_static)."""
from .base import *  # noqa: F401,F403
from .base import BASE_DIR, env

DEBUG = False
SITE_MODE = "demo"
SITE_NOINDEX = True
SHOW_SAMPLE_REVIEWS = True
BASE_PATH = "/" + env("PAGES_BASE_PATH", "Moto-site.io").strip("/") + "/"
SITE_DOMAIN = env("SITE_DOMAIN", "https://azat725.github.io/Moto-site.io").rstrip("/")
FORCE_SCRIPT_NAME = BASE_PATH.rstrip("/")
STATIC_URL = BASE_PATH + "static/"
MEDIA_URL = BASE_PATH + "media/"
MEDIA_ROOT = BASE_DIR / "data" / "pages-media"
DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": BASE_DIR / "data" / "pages-build.sqlite3"}}
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}
MAILERS = {"default": {"BACKEND": "django.core.mail.backends.locmem.EmailBackend"}}
