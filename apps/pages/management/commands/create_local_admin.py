"""Создание администратора исключительно в отдельной локальной песочнице."""
import secrets
from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction


class Command(BaseCommand):
    help = "Создать тестового суперпользователя в data/admin-sandbox (только config.settings.dev)."

    def add_arguments(self, parser):
        parser.add_argument("--username", default="local-admin")

    def handle(self, *args, **options):
        database = settings.DATABASES["default"]
        sandbox = (settings.BASE_DIR / "data" / "admin-sandbox" / "db.sqlite3").resolve()
        if (not settings.DEBUG or settings.SETTINGS_MODULE != "config.settings.dev"
                or database["ENGINE"] != "django.db.backends.sqlite3"
                or Path(database["NAME"]).resolve() != sandbox):
            raise CommandError("Разрешено только локально: config.settings.dev, DEBUG=True, "
                               "DATA_DIR=<проект>/data/admin-sandbox. На сервере используйте createsuperuser.")
        username = options["username"]
        user_model = get_user_model()
        try:
            user_model._meta.get_field("username").clean(username, None)
        except ValidationError as exc:
            raise CommandError("Укажите корректный логин: до 150 символов, без пробелов.") from exc
        with transaction.atomic():
            if user_model.objects.filter(username=username).exists():
                raise CommandError("Такой пользователь уже существует. Пароль и данные не изменены.")
            password = secrets.token_urlsafe(24)
            user_model.objects.create_superuser(username=username, password=password)
        self.stdout.write(f"Логин: {username}\nПароль: {password}\nПароль показан только здесь; сохраните его в менеджере паролей.")
