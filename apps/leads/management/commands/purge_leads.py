from datetime import timedelta

from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.leads.models import Lead


class Command(BaseCommand):
    help = "Обезличить заявки старше LEAD_RETENTION_DAYS (срок хранения персональных данных)."

    def handle(self, *args, **options):
        border = timezone.now() - timedelta(days=settings.LEAD_RETENTION_DAYS)
        count = Lead.objects.filter(created_at__lt=border, anonymized_at__isnull=True).update(
            name="—", phone="—", message="", ip_hash="", anonymized_at=timezone.now()
        )
        self.stdout.write(f"Обезличено заявок: {count}")
