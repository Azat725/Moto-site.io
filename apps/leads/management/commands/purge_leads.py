from datetime import timedelta

from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.leads.models import Lead
from apps.leads.services import anonymize_leads
from apps.reviews.models import Review

REJECTED_REVIEWS_KEEP_DAYS = 90


class Command(BaseCommand):
    help = ("Срок хранения ПДн: обезличить заявки старше LEAD_RETENTION_DAYS и удалить отклонённые отзывы "
            f"старше {REJECTED_REVIEWS_KEEP_DAYS} дней.")

    def handle(self, *args, **options):
        now = timezone.now()
        border = now - timedelta(days=settings.LEAD_RETENTION_DAYS)
        count = anonymize_leads(Lead.objects.filter(created_at__lt=border, anonymized_at__isnull=True))
        spam, _ = Lead.objects.filter(status=Lead.Status.SPAM, created_at__lt=now - timedelta(days=30)).delete()
        removed, _ = Review.objects.filter(
            status=Review.Status.REJECTED, created_at__lt=now - timedelta(days=REJECTED_REVIEWS_KEEP_DAYS)
        ).delete()
        self.stdout.write(f"Обезличено заявок: {count}; удалено спам-заявок: {spam}; "
                          f"удалено отклонённых отзывов: {removed}")
