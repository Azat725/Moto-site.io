import signal
import time

from django.core.management.base import BaseCommand
from django.db import close_old_connections

from apps.leads.delivery import process_due


class Command(BaseCommand):
    help = ("Отправить уведомления из очереди (Telegram, e-mail). "
            "На сервере запускается как постоянный сервис: send_notifications --loop")

    def add_arguments(self, parser):
        parser.add_argument("--loop", action="store_true", help="Работать постоянно, проверяя очередь")
        parser.add_argument("--interval", type=float, default=5.0, help="Пауза между проверками, сек")

    def handle(self, *args, **options):
        if not options["loop"]:
            sent, failed = process_due()
            self.stdout.write(f"Отправлено: {sent}, с ошибкой (будет повтор): {failed}")
            return
        running = {"on": True}
        signal.signal(signal.SIGTERM, lambda *_: running.update(on=False))
        while running["on"]:
            close_old_connections()
            process_due()
            time.sleep(options["interval"])
