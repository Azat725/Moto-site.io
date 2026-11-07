from django.core.management.base import BaseCommand

from apps.leads.notifiers import process_due


class Command(BaseCommand):
    help = "Отправить уведомления из очереди (Telegram, e-mail). Запускается по таймеру раз в минуту."

    def handle(self, *args, **options):
        sent, failed = process_due()
        self.stdout.write(f"Отправлено: {sent}, с ошибкой (будет повтор): {failed}")
