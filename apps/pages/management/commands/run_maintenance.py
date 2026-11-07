"""Плановые команды для Docker без cron, systemd и дополнительных зависимостей."""
from datetime import timedelta
import logging
import signal
from threading import Event

from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.db import close_old_connections
from django.utils import timezone

logger = logging.getLogger(__name__)


def next_daily(now, hour, minute):
    target = timezone.localtime(now).replace(hour=hour, minute=minute, second=0, microsecond=0)
    return target if target > now else target + timedelta(days=1)


class Command(BaseCommand):
    help = "Обновлять курс каждые 3 часа, резервировать в 03:30 и выполнять политику хранения в 04:15 (МСК)."

    def add_arguments(self, parser):
        parser.add_argument("--once", action="store_true", help="Выполнить готовые задачи один раз и выйти")

    def handle(self, *args, **options):
        stop = Event()
        if not options["once"]:
            for sig in (signal.SIGTERM, signal.SIGINT):
                signal.signal(sig, lambda *_: stop.set())
        now = timezone.now()
        due = {"update_rate": now, "backup_site": next_daily(now, 3, 30), "purge_leads": next_daily(now, 4, 15)}
        while not stop.is_set():
            close_old_connections()
            now = timezone.now()
            for name, deadline in tuple(due.items()):
                if now < deadline:
                    continue
                try:
                    call_command(name, **({"soft": True} if name == "update_rate" else {}))
                except Exception:
                    # Имя задачи достаточно для диагностики; тексты исключений могут содержать секреты/ПДн.
                    logger.error("Плановая задача %s завершилась ошибкой; проверьте настройки и диск.", name)
                due[name] = (now + timedelta(hours=3) if name == "update_rate"
                             else next_daily(now, 3, 30) if name == "backup_site" else next_daily(now, 4, 15))
            if options["once"]:
                break
            stop.wait(30)
