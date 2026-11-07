"""Подготовка контейнеров после остановки всех процессов записи в SQLite."""
from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Создать копию существующей базы, проверить production, применить миграции и собрать статику."
    requires_system_checks = []

    def handle(self, *args, **options):
        settings.DATA_DIR.mkdir(parents=True, exist_ok=True)
        settings.MEDIA_ROOT.mkdir(parents=True, exist_ok=True)
        database = settings.DATA_DIR / "db.sqlite3"
        if database.is_file() and database.stat().st_size:
            call_command("backup_site")
        call_command("check", deploy=True, fail_level="WARNING")
        call_command("migrate", interactive=False)
        call_command("collectstatic", interactive=False)
