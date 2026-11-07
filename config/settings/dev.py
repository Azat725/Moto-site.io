"""Локальная разработка."""
from .base import *  # noqa: F401,F403
from .base import env_bool

DEBUG = env_bool("DJANGO_DEBUG", True)
EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
SHOW_SAMPLE_REVIEWS = env_bool("SHOW_SAMPLE_REVIEWS", True)
