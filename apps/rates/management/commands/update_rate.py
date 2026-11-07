from django.core.management.base import BaseCommand, CommandError

from apps.rates.services import refresh_rate


class Command(BaseCommand):
    help = "Получить актуальный курс USD/RUB с сайта ЦБ РФ (запускается по таймеру каждые 3 часа)."

    def add_arguments(self, parser):
        parser.add_argument("--soft", action="store_true", help="Не завершаться с ошибкой, если курс получить не удалось")

    def handle(self, *args, **options):
        result = refresh_rate()
        if result.ok:
            self.stdout.write(self.style.SUCCESS(result.message))
            return
        if options["soft"]:
            self.stderr.write(self.style.WARNING(result.message))
            return
        raise CommandError(result.message)
