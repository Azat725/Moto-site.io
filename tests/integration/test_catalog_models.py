"""Модели каталога и обработка фото (проверка формата, WebP, прозрачность)."""
import io

import pytest
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError, transaction
from PIL import Image

from apps.catalog import images
from apps.catalog.images import check_image, normalize_upload
from apps.catalog.models import MotorcycleOption, Photo, Variant
from tests.factories import make_color, make_motorcycle, make_motorcycle_option, make_option_def, make_variant


def image_bytes(fmt="PNG", size=(40, 20), mode="RGB", color=(225, 6, 0)) -> bytes:
    buffer = io.BytesIO()
    fill = (*color, 128) if mode == "RGBA" else color
    Image.new(mode, size, fill).save(buffer, format=fmt)
    return buffer.getvalue()


class TestCheckImage:
    @pytest.mark.parametrize("fmt", ["PNG", "JPEG", "WEBP"])
    def test_allowed_formats_pass_and_rewind(self, fmt):
        upload = io.BytesIO(image_bytes(fmt))
        upload.seek(5)

        check_image(upload)

        assert upload.tell() == 0

    def test_gif_rejected(self):
        with pytest.raises(ValidationError, match="JPEG, PNG или WebP"):
            check_image(io.BytesIO(image_bytes("GIF", mode="P", color=1)))

    def test_not_an_image(self):
        with pytest.raises(ValidationError, match="не является изображением"):
            check_image(io.BytesIO(b"%PDF-1.7 not an image"))

    def test_too_many_bytes(self):
        upload = SimpleUploadedFile("x.png", image_bytes())
        upload.size = images.MAX_BYTES + 1
        with pytest.raises(ValidationError, match="10 МБ"):
            check_image(upload)

    def test_too_many_pixels(self, monkeypatch):
        monkeypatch.setattr(images, "MAX_PIXELS", 100)
        with pytest.raises(ValidationError, match="разрешение"):
            check_image(io.BytesIO(image_bytes(size=(20, 20))))


class _FieldFile:
    def __init__(self, data: bytes):
        self.file = io.BytesIO(data)


class TestNormalizeUpload:
    def _open(self, upload):
        upload.seek(0)
        return Image.open(io.BytesIO(upload.read()))

    def test_jpeg_becomes_rgb_webp(self):
        result = normalize_upload(_FieldFile(image_bytes("JPEG")))

        assert result.name.endswith(".webp") and result.content_type == "image/webp"
        with self._open(result) as img:
            assert img.format == "WEBP" and img.mode == "RGB"

    def test_png_transparency_kept(self):
        result = normalize_upload(_FieldFile(image_bytes("PNG", mode="RGBA")))
        with self._open(result) as img:
            assert img.mode == "RGBA"

    def test_transparent_palette_png_keeps_alpha(self):
        buffer = io.BytesIO()
        palette_img = Image.new("P", (10, 10), 0)
        palette_img.putpalette([0, 0, 0, 225, 6, 0] + [0] * 762)
        palette_img.putpixel((0, 0), 1)  # один видимый красный пиксель, остальное — прозрачный индекс 0
        palette_img.save(buffer, format="PNG", transparency=0)
        with self._open(normalize_upload(_FieldFile(buffer.getvalue()))) as img:
            assert img.mode == "RGBA"

    def test_downscaled_to_max_side(self):
        result = normalize_upload(_FieldFile(image_bytes("PNG", size=(3600, 900))))
        with self._open(result) as img:
            assert img.size == (1800, 450)

    def test_random_unique_names(self):
        a = normalize_upload(_FieldFile(image_bytes()))
        b = normalize_upload(_FieldFile(image_bytes()))
        assert a.name != b.name

    def test_invalid_file_raises(self):
        with pytest.raises(ValidationError):
            normalize_upload(_FieldFile(b"nope"))


@pytest.mark.django_db
class TestPhotoModel:
    def test_save_normalises_and_records_size(self, settings, tmp_path):
        settings.MEDIA_ROOT = tmp_path
        moto = make_motorcycle(slug="storm")
        photo = Photo(motorcycle=moto, alt="Storm", image=SimpleUploadedFile("p.png", image_bytes(size=(64, 32))))

        photo.save()

        photo.refresh_from_db()
        assert photo.image.name.startswith("bikes/storm/") and photo.image.name.endswith(".webp")
        assert (photo.width, photo.height) == (64, 32)
        assert str(photo) == "Storm"

    def test_validator_rejects_non_image_in_full_clean(self, settings, tmp_path):
        settings.MEDIA_ROOT = tmp_path
        photo = Photo(motorcycle=make_motorcycle(), alt="x", image=SimpleUploadedFile("p.png", b"not image"))

        with pytest.raises(ValidationError) as exc:
            photo.full_clean()

        assert "image" in exc.value.message_dict


@pytest.mark.django_db
class TestCatalogModels:
    def test_variant_label_unique_per_motorcycle(self):
        moto = make_motorcycle()
        make_variant(moto, label="Base")
        make_variant(make_motorcycle(), label="Base")  # у другой модели — можно

        with pytest.raises(IntegrityError), transaction.atomic():
            make_variant(moto, label="Base")

    def test_motorcycle_option_unique(self):
        moto, option = make_motorcycle(), make_option_def()
        make_motorcycle_option(moto, option)
        with pytest.raises(IntegrityError), transaction.atomic():
            make_motorcycle_option(moto, option)

    def test_optional_option_requires_price(self):
        option = MotorcycleOption(motorcycle=make_motorcycle(), option=make_option_def(),
                                  status=MotorcycleOption.Status.OPTIONAL, price_usd=None)
        with pytest.raises(ValidationError) as exc:
            option.clean()
        assert "price_usd" in exc.value.message_dict

    def test_included_option_without_price_ok(self):
        MotorcycleOption(motorcycle=make_motorcycle(), option=make_option_def(),
                         status=MotorcycleOption.Status.INCLUDED, price_usd=None).clean()

    def test_variant_spec_falls_back_to_motorcycle(self):
        moto = make_motorcycle(motor_power_w=5000, brakes="Диски")
        variant = make_variant(moto, motor_power_w=8000, brakes="")

        assert variant.spec("motor_power_w") == 8000
        assert variant.spec("brakes") == "Диски"
        assert variant.spec("top_speed_kmh") == moto.top_speed_kmh

    def test_motorcycle_helpers(self):
        moto = make_motorcycle(slug="storm", name="Storm", motor_power_w=7500,
                               description="Первый.\n\n\n Второй. \n\n", features="ABS\n \nLED\n")

        assert moto.power_kw == "7.5"
        assert moto.description_paragraphs == ["Первый.", "Второй."]
        assert moto.feature_list == ["ABS", "LED"]
        assert moto.get_absolute_url() == "/moto/storm/"
        assert str(moto) == "Storm"

    def test_str_methods(self):
        moto = make_motorcycle(name="Storm")
        option = make_option_def(name="ABS")
        assert str(make_variant(moto, label="V1")) == "Storm — V1"
        assert str(make_motorcycle_option(moto, option)) == "Storm: ABS"
        assert str(option) == "ABS"
        assert str(make_color(name="Красный")) == "Красный"

    def test_variant_ordering(self):
        moto = make_motorcycle()
        second = make_variant(moto, sort_order=20)
        first = make_variant(moto, sort_order=10)
        assert list(Variant.objects.filter(motorcycle=moto)) == [first, second]
