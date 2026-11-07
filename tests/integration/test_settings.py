"""Проверки прод-настроек выполняются в отдельном процессе, чтобы не трогать настройки тестового прогона."""
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
GOOD_ENV = {"DJANGO_SECRET_KEY": "x" * 64, "IP_HASH_SALT": "salt-for-tests-" * 3,
            "ADMIN_PATH": "secret-panel-42/", "DJANGO_ALLOWED_HOSTS": "example.com",
            "DJANGO_CSRF_TRUSTED_ORIGINS": "https://example.com"}


def _import_prod(**env):
    full_env = {k: v for k, v in os.environ.items() if k not in {"ADMIN_PATH", "DJANGO_SECRET_KEY", "IP_HASH_SALT"}}
    full_env.update(env)
    code = "import config.settings.prod as p; print(p.ADMIN_PATH)"
    return subprocess.run([sys.executable, "-c", code], cwd=ROOT, env=full_env, capture_output=True, text=True,
                          timeout=60)


@pytest.mark.parametrize("admin_path", ["manage-ivax/", "admin", "/"])
def test_prod_rejects_default_or_public_admin_path(admin_path):
    result = _import_prod(**{**GOOD_ENV, "ADMIN_PATH": admin_path})
    assert result.returncode != 0
    assert "ImproperlyConfigured" in result.stderr and "ADMIN_PATH" in result.stderr


def test_prod_rejects_missing_admin_path():
    env = {k: v for k, v in GOOD_ENV.items() if k != "ADMIN_PATH"}
    assert "ADMIN_PATH" in _import_prod(**env).stderr


def test_prod_rejects_weak_secret_key():
    result = _import_prod(**{**GOOD_ENV, "DJANGO_SECRET_KEY": "short"})
    assert result.returncode != 0 and "DJANGO_SECRET_KEY" in result.stderr


def test_prod_accepts_custom_admin_path():
    result = _import_prod(**GOOD_ENV)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "secret-panel-42/"


@pytest.mark.parametrize("variable,value", [
    ("IP_HASH_SALT", ""), ("IP_HASH_SALT", "short"),
    ("DJANGO_ALLOWED_HOSTS", ""), ("DJANGO_ALLOWED_HOSTS", "*"),
    ("DJANGO_ALLOWED_HOSTS", "localhost"), ("DJANGO_ALLOWED_HOSTS", "https://example.com"),
    ("DJANGO_CSRF_TRUSTED_ORIGINS", ""), ("DJANGO_CSRF_TRUSTED_ORIGINS", "http://example.com"),
    ("DJANGO_CSRF_TRUSTED_ORIGINS", "https://other.example"),
    ("ADMIN_PATH", "../catalog/"), ("ADMIN_PATH", "api/"), ("ADMIN_PATH", "with spaces in path/"),
])
def test_prod_rejects_unsafe_configuration(variable, value):
    result = _import_prod(**{**GOOD_ENV, variable: value})
    assert result.returncode != 0 and variable in result.stderr
