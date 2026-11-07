"""Каталог электромотоциклов: модели, варианты (мощность/АКБ), опции, цвета, фото, настройки цен."""
from __future__ import annotations

from decimal import Decimal

from django.core.validators import MinValueValidator, RegexValidator
from django.db import models

slug_validator = RegexValidator(r"^[a-z0-9]+(?:-[a-z0-9]+)*$", "Только латиница в нижнем регистре, цифры и дефисы.")
code_validator = RegexValidator(r"^[a-z0-9_]{2,40}$", "Только латиница в нижнем регистре, цифры и _.")
hex_validator = RegexValidator(r"^#[0-9A-Fa-f]{6}$", "Цвет в формате #RRGGBB.")


class SiteSettings(models.Model):
    """Единственная запись (pk=1) с настройками цен и контактами, которые владелец меняет в админке."""

    class RateMode(models.TextChoices):
        AUTO = "auto", "Автоматически по курсу ЦБ РФ"
        MANUAL = "manual", "Вручную"

    markup_rub = models.PositiveIntegerField("Наценка, ₽", default=100_000)
    rounding_step = models.PositiveIntegerField(
        "Округление цены вверх до, ₽",
        default=1000,
        choices=[(1, "1 ₽"), (10, "10 ₽"), (100, "100 ₽"), (500, "500 ₽"), (1000, "1 000 ₽"), (5000, "5 000 ₽")],
    )
    rate_mode = models.CharField("Курс доллара", max_length=10, choices=RateMode.choices, default=RateMode.AUTO)
    manual_rate = models.DecimalField(
        "Ручной курс, ₽ за $", max_digits=10, decimal_places=4, null=True, blank=True,
        validators=[MinValueValidator(Decimal("1"))],
    )
    phone = models.CharField("Телефон", max_length=40, default="+7 (900) 000-00-00")
    email = models.EmailField("E-mail для клиентов", default="info@ivax-moto.ru")
    address = models.CharField("Адрес", max_length=200, default="г. Нижнекамск, [улица, дом]")
    hours = models.CharField("Режим работы", max_length=120, default="Пн–Сб 10:00–20:00, Вс 11:00–18:00")
    legal_name = models.CharField(
        "Продавец (юрлицо / ИП)", max_length=250,
        default="[Полное наименование юридического лица / ФИО индивидуального предпринимателя]",
    )
    inn = models.CharField("ИНН", max_length=20, default="[ИНН]")
    ogrn = models.CharField("ОГРН / ОГРНИП", max_length=20, default="[ОГРН / ОГРНИП]")
    telegram_url = models.URLField("Telegram (ссылка для клиентов)", blank=True)
    vk_url = models.URLField("ВКонтакте", blank=True)
    whatsapp_url = models.URLField("WhatsApp", blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Настройки сайта"
        verbose_name_plural = "Настройки сайта"

    def __str__(self) -> str:
        return "Настройки сайта"

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def load(cls) -> "SiteSettings":
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    @property
    def phone_raw(self) -> str:
        digits = "".join(ch for ch in self.phone if ch.isdigit())
        return "+" + digits if digits else ""


class Motorcycle(models.Model):
    class Type(models.TextChoices):
        SPORT = "sport", "Спорт"
        NAKED = "naked", "Нейкед"
        CRUISER = "cruiser", "Круизер"
        TOURING = "touring", "Туринг"

    class Drive(models.TextChoices):
        CHAIN = "chain", "Цепь"
        BELT = "belt", "Ремень"

    class Cooling(models.TextChoices):
        AIR = "air", "Воздушное"
        LIQUID = "liquid", "Жидкостное"

    slug = models.SlugField("Адрес страницы (slug)", max_length=60, unique=True, validators=[slug_validator])
    name = models.CharField("Название модели", max_length=60)
    line = models.CharField("Линейка", max_length=20, blank=True, help_text="Например, M или MX")
    type = models.CharField("Тип", max_length=10, choices=Type.choices, default=Type.SPORT)
    short = models.CharField("Короткое описание", max_length=200, blank=True)
    description = models.TextField("Описание", blank=True, help_text="Абзацы разделяйте пустой строкой.")
    features = models.TextField("Особенности", blank=True, help_text="По одной на строку.")
    origin_country = models.CharField("Страна производства", max_length=40, default="Китай")
    supplier_ref = models.CharField(
        "Внутренний код поставщика", max_length=60, blank=True, help_text="На сайте не показывается."
    )
    motor_power_w = models.PositiveIntegerField("Мощность мотора, Вт", default=5000)
    motor_layout = models.CharField("Расположение мотора", max_length=60, default="Центральный")
    drive = models.CharField("Привод", max_length=10, choices=Drive.choices, default=Drive.CHAIN)
    cooling = models.CharField("Охлаждение", max_length=10, choices=Cooling.choices, default=Cooling.AIR)
    voltage_v = models.PositiveIntegerField("Напряжение АКБ, В", default=72)
    battery_type = models.CharField("Тип АКБ", max_length=60, default="Литиевая")
    top_speed_kmh = models.PositiveIntegerField("Максимальная скорость, км/ч", default=130)
    range_min_km = models.PositiveIntegerField("Запас хода от, км", default=120)
    range_max_km = models.PositiveIntegerField("Запас хода до, км", default=230)
    brakes = models.CharField("Тормоза", max_length=120, default="Дисковые спереди и сзади")
    suspension_front = models.CharField("Передняя подвеска", max_length=120, default="Гидравлическая")
    suspension_rear = models.CharField("Задняя подвеска", max_length=120, default="Гидравлическая с пружиной")
    tyre_front = models.CharField("Передняя шина", max_length=40, default="110/70-17")
    tyre_rear = models.CharField("Задняя шина", max_length=60, default="140/70-17")
    tyre_kind = models.CharField("Шины", max_length=40, default="Бескамерные")
    colors = models.ManyToManyField("Color", verbose_name="Доступные цвета", blank=True)
    is_published = models.BooleanField("Опубликована", default=False)
    is_popular = models.BooleanField("Популярная", default=False)
    sort_order = models.PositiveIntegerField("Порядок", default=100)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Электромотоцикл"
        verbose_name_plural = "Электромотоциклы"
        ordering = ["sort_order", "name"]

    def __str__(self) -> str:
        return self.name

    def get_absolute_url(self) -> str:
        from django.urls import reverse

        return reverse("pages:model", kwargs={"slug": self.slug})

    @property
    def power_kw(self) -> str:
        return f"{self.motor_power_w / 1000:g}"

    @property
    def description_paragraphs(self) -> list[str]:
        return [p.strip() for p in self.description.split("\n\n") if p.strip()]

    @property
    def feature_list(self) -> list[str]:
        return [f.strip() for f in self.features.splitlines() if f.strip()]


class Variant(models.Model):
    """Комплектация по мощности и батарее. Пустые поля берутся из модели."""

    motorcycle = models.ForeignKey(Motorcycle, on_delete=models.CASCADE, related_name="variants")
    label = models.CharField("Название варианта", max_length=80, help_text="Например: 5 кВт · 72 В 100 А·ч")
    battery_ah = models.PositiveIntegerField("Ёмкость АКБ, А·ч")
    voltage_v = models.PositiveIntegerField("Напряжение, В", null=True, blank=True)
    motor_power_w = models.PositiveIntegerField("Мощность, Вт", null=True, blank=True)
    drive = models.CharField("Привод", max_length=10, choices=Motorcycle.Drive.choices, blank=True)
    top_speed_kmh = models.PositiveIntegerField("Скорость, км/ч", null=True, blank=True)
    range_max_km = models.PositiveIntegerField("Запас хода до, км", null=True, blank=True)
    brakes = models.CharField("Тормоза", max_length=120, blank=True)
    tyre_rear = models.CharField("Задняя шина", max_length=60, blank=True)
    price_usd = models.DecimalField(
        "Цена поставщика, $", max_digits=10, decimal_places=2, null=True, blank=True,
        validators=[MinValueValidator(Decimal("0"))], help_text="Пусто — «цена по запросу».",
    )
    sort_order = models.PositiveIntegerField("Порядок", default=10)

    class Meta:
        verbose_name = "Вариант (мощность / АКБ)"
        verbose_name_plural = "Варианты (мощность / АКБ)"
        ordering = ["sort_order", "id"]
        constraints = [models.UniqueConstraint(fields=["motorcycle", "label"], name="uniq_variant_label")]

    def __str__(self) -> str:
        return f"{self.motorcycle.name} — {self.label}"

    def spec(self, field: str):
        own = getattr(self, field, None)
        return own if own not in (None, "") else getattr(self.motorcycle, field)


class OptionDef(models.Model):
    code = models.CharField("Код", max_length=40, unique=True, validators=[code_validator])
    name = models.CharField("Название", max_length=120)
    description = models.CharField("Пояснение", max_length=250, blank=True)
    sort_order = models.PositiveIntegerField("Порядок", default=100)

    class Meta:
        verbose_name = "Опция (справочник)"
        verbose_name_plural = "Опции (справочник)"
        ordering = ["sort_order", "name"]

    def __str__(self) -> str:
        return self.name


class MotorcycleOption(models.Model):
    class Status(models.TextChoices):
        OPTIONAL = "optional", "За доплату"
        INCLUDED = "included", "Входит в комплектацию"

    motorcycle = models.ForeignKey(Motorcycle, on_delete=models.CASCADE, related_name="options")
    option = models.ForeignKey(OptionDef, on_delete=models.PROTECT, verbose_name="Опция")
    status = models.CharField("Статус", max_length=10, choices=Status.choices, default=Status.OPTIONAL)
    price_usd = models.DecimalField(
        "Цена, $", max_digits=10, decimal_places=2, null=True, blank=True,
        validators=[MinValueValidator(Decimal("0"))],
    )

    class Meta:
        verbose_name = "Опция модели"
        verbose_name_plural = "Опции модели"
        ordering = ["option__sort_order", "option__name"]
        constraints = [models.UniqueConstraint(fields=["motorcycle", "option"], name="uniq_motorcycle_option")]

    def __str__(self) -> str:
        return f"{self.motorcycle.name}: {self.option.name}"

    @property
    def is_included(self) -> bool:
        return self.status == self.Status.INCLUDED

    def clean(self):
        from django.core.exceptions import ValidationError

        if self.status == self.Status.OPTIONAL and self.price_usd is None:
            raise ValidationError({"price_usd": "Укажите цену опции или отметьте «Входит в комплектацию»."})


class Color(models.Model):
    code = models.CharField("Код", max_length=40, unique=True, validators=[code_validator])
    name = models.CharField("Название", max_length=60)
    hex = models.CharField("Цвет", max_length=7, validators=[hex_validator])
    sort_order = models.PositiveIntegerField("Порядок", default=100)

    class Meta:
        verbose_name = "Цвет"
        verbose_name_plural = "Цвета"
        ordering = ["sort_order", "name"]

    def __str__(self) -> str:
        return self.name


def validate_image_file(field_file) -> None:
    """Проверка в форме админки (ошибка покажется у поля, а не 500)."""
    from .images import check_image

    if field_file and not getattr(field_file, "_committed", True):
        check_image(field_file.file)


def photo_upload_to(instance: "Photo", filename: str) -> str:
    return f"bikes/{instance.motorcycle.slug}/{filename}"


class Photo(models.Model):
    motorcycle = models.ForeignKey(Motorcycle, on_delete=models.CASCADE, related_name="photos")
    image = models.ImageField("Фото", upload_to=photo_upload_to, validators=[validate_image_file])
    alt = models.CharField("Описание для поисковиков (alt)", max_length=160)
    width = models.PositiveIntegerField(editable=False, default=0)
    height = models.PositiveIntegerField(editable=False, default=0)
    sort_order = models.PositiveIntegerField("Порядок", default=10)

    class Meta:
        verbose_name = "Фото"
        verbose_name_plural = "Фото"
        ordering = ["sort_order", "id"]

    def __str__(self) -> str:
        return self.alt

    def save(self, *args, **kwargs):
        from .images import normalize_upload

        if self.image and not getattr(self.image, "_committed", True):
            self.image = normalize_upload(self.image)
        super().save(*args, **kwargs)
        if self.image and (not self.width or not self.height):
            self.width, self.height = self.image.width, self.image.height
            super().save(update_fields=["width", "height"])
