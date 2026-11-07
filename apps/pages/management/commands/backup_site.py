"""Согласованная SQLite-копия и архив фото без остановки чтения сайта."""
import json
import os
from contextlib import closing
from pathlib import Path
import secrets
import sqlite3
import tarfile

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import connections
from django.utils import timezone


class Command(BaseCommand):
    help = "Создать резервную копию SQLite и media в BACKUP_DIR; исходные данные не изменяются."
    requires_system_checks = []

    def handle(self, *args, **options):
        db = connections["default"]
        if db.vendor != "sqlite" or db.in_atomic_block:
            raise CommandError("Резервирование поддерживает SQLite вне активной транзакции.")
        root = Path(os.environ.get("BACKUP_DIR", str(settings.DATA_DIR / "backups")))
        now = timezone.now()
        name = f"site-{now:%Y%m%dT%H%M%SZ}-{secrets.token_hex(4)}"
        staging, destination = root / (".incomplete-" + name), root / name
        root.mkdir(parents=True, exist_ok=True, mode=0o700)
        staging.mkdir(mode=0o700)
        try:
            db.ensure_connection()
            with closing(sqlite3.connect(staging / "db.sqlite3")) as target:
                db.connection.backup(target)
            with tarfile.open(staging / "media.tar.gz", "w:gz") as archive:
                if settings.MEDIA_ROOT.is_dir():
                    archive.add(settings.MEDIA_ROOT, arcname="media")
            (staging / "metadata.json").write_text(json.dumps({"created_at": now.isoformat()}), encoding="utf-8")
            for file in staging.iterdir():
                file.chmod(0o600)
            staging.rename(destination)
        except (OSError, sqlite3.Error, tarfile.TarError) as exc:
            raise CommandError("Резервная копия не завершена; проверьте диск и права. Миграции не запускайте.") from exc
        self.stdout.write(f"Резервная копия создана: {destination.name}")
