"""Команда не трогает production и никогда не перезаписывает существующего пользователя."""
from io import StringIO
from types import SimpleNamespace

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

pytestmark = pytest.mark.django_db


def allow_sandbox(settings, monkeypatch):
    # Подменяем только вход защитной проверки; ORM продолжает работать с изолированной базой pytest.
    config = SimpleNamespace(DEBUG=True, SETTINGS_MODULE="config.settings.dev", BASE_DIR=settings.BASE_DIR,
                             DATABASES={"default": {"ENGINE": "django.db.backends.sqlite3",
                                                    "NAME": settings.BASE_DIR / "data/admin-sandbox/db.sqlite3"}})
    monkeypatch.setattr("apps.pages.management.commands.create_local_admin.settings", config)


def test_local_admin_is_generated_and_password_is_hashed(settings, django_user_model, monkeypatch):
    allow_sandbox(settings, monkeypatch)
    output = StringIO()
    call_command("create_local_admin", stdout=output)
    password = output.getvalue().split("Пароль: ", 1)[1].splitlines()[0]
    user = django_user_model.objects.get(username="local-admin")
    assert user.is_staff and user.is_superuser and user.is_active
    assert len(password) >= 24 and user.password != password and user.check_password(password)


@pytest.mark.parametrize("debug,module", [(False, "config.settings.prod"), (True, "config.settings.prod")])
def test_local_admin_refuses_production(settings, django_user_model, debug, module):
    settings.DEBUG, settings.SETTINGS_MODULE = debug, module
    with pytest.raises(CommandError):
        call_command("create_local_admin")
    assert not django_user_model.objects.exists()


def test_local_admin_refuses_regular_database(settings):
    settings.DEBUG, settings.SETTINGS_MODULE = True, "config.settings.dev"
    with pytest.raises(CommandError):
        call_command("create_local_admin")


def test_local_admin_never_resets_existing_password(settings, django_user_model, monkeypatch):
    allow_sandbox(settings, monkeypatch)
    user = django_user_model.objects.create_superuser("local-admin", password="existing-test-password")
    with pytest.raises(CommandError, match="уже существует"):
        call_command("create_local_admin")
    user.refresh_from_db()
    assert user.check_password("existing-test-password")


@pytest.mark.parametrize("username", ["", "bad name with spaces", "a" * 151])
def test_local_admin_validates_username(settings, django_user_model, monkeypatch, username):
    allow_sandbox(settings, monkeypatch)
    with pytest.raises(CommandError, match="логин"):
        call_command("create_local_admin", username=username)
    assert not django_user_model.objects.exists()
