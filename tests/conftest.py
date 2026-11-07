"""Общие фикстуры: без сети (responses), чистый кэш, фиксированное время, админ-клиент."""
from __future__ import annotations

from datetime import datetime, timezone as dt_timezone

import pytest
import responses as responses_lib
from django.core.cache import cache
from django.utils import timezone

FROZEN_NOW = datetime(2026, 11, 7, 9, 0, tzinfo=dt_timezone.utc)  # 12:00 по Москве


@pytest.fixture(autouse=True)
def rsps():
    """Любой HTTP-запрос через requests без зарегистрированного ответа падает с ConnectionError."""
    with responses_lib.RequestsMock(assert_all_requests_are_fired=False) as mock:
        yield mock


@pytest.fixture(autouse=True)
def _clear_cache():
    cache.clear()
    yield
    cache.clear()


class Clock:
    def __init__(self, monkeypatch, start: datetime):
        self.current = start
        monkeypatch.setattr(timezone, "now", lambda: self.current)

    def set(self, value: datetime) -> None:
        self.current = value


@pytest.fixture
def clock(monkeypatch) -> Clock:
    """Замораживает django.utils.timezone.now (и localdate) на FROZEN_NOW; clock.set() переводит время."""
    return Clock(monkeypatch, FROZEN_NOW)


@pytest.fixture
def admin_prefix(settings) -> str:
    return "/" + settings.ADMIN_PATH


@pytest.fixture
def superuser(django_user_model):
    return django_user_model.objects.create_superuser("boss", "boss@example.com", "very-secret-password-123")


@pytest.fixture
def admin_client_logged(client, superuser):
    client.force_login(superuser)
    return client
