from django.core.management.base import BaseCommand

from apps.catalog.seed_loader import seed_catalog


class Command(BaseCommand):
    help = "Загрузить/обновить каталог из apps/catalog/seed/catalog.json (прайс поставщика) и фото."

    def add_arguments(self, parser):
        parser.add_argument("--no-photos", action="store_true", help="Не прикреплять фото")

    def handle(self, *args, **options):
        count = seed_catalog(with_photos=not options["no_photos"])
        self.stdout.write(self.style.SUCCESS(f"Каталог загружен: моделей — {count}"))
