from django.db import models


class Lead(models.Model):
    class Status(models.TextChoices):
        NEW = "new", "Новая"
        IN_PROGRESS = "in_progress", "В работе"
        DONE = "done", "Завершена"
        CANCELLED = "cancelled", "Отменена"
        SPAM = "spam", "Спам"

    class Kind(models.TextChoices):
        MODEL = "model", "Конфигурация модели"
        CALLBACK = "callback", "Обратный звонок"
        CONTACT = "contact", "Сообщение"

    class Way(models.TextChoices):
        CALL = "call", "Позвонить"
        MESSENGER = "messenger", "Написать в мессенджер"

    created_at = models.DateTimeField("Создана", auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)
    status = models.CharField("Статус", max_length=12, choices=Status.choices, default=Status.NEW, db_index=True)
    kind = models.CharField("Тип", max_length=10, choices=Kind.choices, default=Kind.CALLBACK)
    name = models.CharField("Имя", max_length=80)
    phone = models.CharField("Телефон", max_length=20)
    message = models.TextField("Комментарий", blank=True, max_length=600)
    contact_way = models.CharField("Способ связи", max_length=10, choices=Way.choices, default=Way.CALL)
    motorcycle = models.ForeignKey(
        "catalog.Motorcycle", verbose_name="Модель", on_delete=models.SET_NULL, null=True, blank=True
    )
    model_name = models.CharField("Модель (на момент заявки)", max_length=80, blank=True)
    config = models.JSONField("Конфигурация", default=dict, blank=True)
    total_rub = models.PositiveIntegerField("Итоговая цена, ₽", null=True, blank=True)
    consent_at = models.DateTimeField("Согласие на обработку ПДн получено")
    consent_version = models.CharField("Версия согласия", max_length=20)
    page = models.CharField("Страница", max_length=200, blank=True)
    ip_hash = models.CharField(max_length=64, blank=True, editable=False)
    manager_note = models.TextField("Заметка менеджера", blank=True)
    anonymized_at = models.DateTimeField("Обезличена", null=True, blank=True, editable=False)

    class Meta:
        verbose_name = "Заявка"
        verbose_name_plural = "Заявки"
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"Заявка №{self.pk} — {self.model_name or self.get_kind_display()}"


class Outbox(models.Model):
    """Очередь уведомлений: заявка сначала сохраняется в БД, затем отправляется с повторами."""

    class Channel(models.TextChoices):
        TELEGRAM = "telegram", "Telegram"
        EMAIL = "email", "E-mail"

    class Status(models.TextChoices):
        PENDING = "pending", "Ожидает"
        SENT = "sent", "Отправлено"
        DEAD = "dead", "Не доставлено"

    channel = models.CharField("Канал", max_length=10, choices=Channel.choices)
    subject = models.CharField("Тема", max_length=200)
    body = models.TextField("Текст")
    lead = models.ForeignKey(Lead, on_delete=models.CASCADE, null=True, blank=True, related_name="notifications")
    status = models.CharField("Статус", max_length=10, choices=Status.choices, default=Status.PENDING, db_index=True)
    attempts = models.PositiveIntegerField("Попыток", default=0)
    next_attempt_at = models.DateTimeField("Следующая попытка", db_index=True)
    last_error = models.CharField("Последняя ошибка", max_length=500, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    sent_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "Уведомление"
        verbose_name_plural = "Уведомления (очередь)"
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.get_channel_display()}: {self.subject}"
