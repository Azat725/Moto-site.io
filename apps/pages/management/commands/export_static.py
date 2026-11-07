"""Статическое демо для GitHub Pages: рендерит все публичные страницы в папку _site/.

Запуск:  DJANGO_SETTINGS_MODULE=config.settings.pages python manage.py export_static
В демо формы не отправляются, отзывы — образцы с пометкой, сайт закрыт от индексации (noindex).
База для сборки — отдельная (data/pages-build.sqlite3), только каталог и курс, без заявок и отзывов.
"""
from __future__ import annotations

import shutil
from pathlib import Path

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.test import Client
from django.urls import reverse

from apps.catalog.models import Motorcycle

STATIC_ROUTES = ("pages:home", "pages:catalog", "pages:delivery", "pages:reviews", "pages:about", "pages:contacts",
                 "pages:privacy", "pages:consent", "pages:consent_publication", "pages:terms", "pages:cookies",
                 "pages:thanks", "pages:preview_home_classic", "pages:preview_logo")


class Command(BaseCommand):
    help = "Собрать статическое демо сайта в _site/ (для GitHub Pages)."

    def add_arguments(self, parser):
        parser.add_argument("--out", default=str(settings.BASE_DIR / "_site"))
        parser.add_argument("--no-rate", action="store_true", help="Не запрашивать курс ЦБ (оффлайн-сборка)")

    def handle(self, *args, **options):
        if settings.SITE_MODE != "demo":
            raise CommandError("Запускайте с DJANGO_SETTINGS_MODULE=config.settings.pages")
        out = Path(options["out"])
        self._prepare_db(options["no_rate"])
        if out.exists():
            shutil.rmtree(out)
        out.mkdir(parents=True)
        pages = self._render_all(out)
        self._copy_assets(out)
        (out / ".nojekyll").write_text("", encoding="utf-8")
        self.stdout.write(self.style.SUCCESS(f"Готово: {pages} страниц в {out}"))

    def _prepare_db(self, no_rate: bool) -> None:
        Path(settings.DATABASES["default"]["NAME"]).parent.mkdir(parents=True, exist_ok=True)
        call_command("migrate", verbosity=0, interactive=False)
        call_command("seed_catalog", verbosity=0)
        if not no_rate:
            call_command("update_rate", "--soft", verbosity=0)

    def _paths(self) -> list[str]:
        prefix = settings.FORCE_SCRIPT_NAME or ""
        paths = [reverse(name) for name in STATIC_ROUTES]
        paths += [m.get_absolute_url() for m in Motorcycle.objects.filter(is_published=True)]
        return [p[len(prefix):] if prefix and p.startswith(prefix) else p for p in paths]

    def _render_all(self, out: Path) -> int:
        client = Client()
        count = 0
        for path in self._paths():
            response = client.get(path)
            if response.status_code != 200:
                raise CommandError(f"{path}: HTTP {response.status_code}")
            target = out / path.strip("/") / "index.html" if path.strip("/") else out / "index.html"
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(response.content)
            count += 1
        for name, path in (("sitemap.xml", "/sitemap.xml"), ("robots.txt", "/robots.txt")):
            (out / name).write_bytes(client.get(path).content)
        missing = client.get("/__not-found__/")
        (out / "404.html").write_bytes(missing.content)
        return count

    def _copy_assets(self, out: Path) -> None:
        for source in settings.STATICFILES_DIRS:
            shutil.copytree(source, out / "static", dirs_exist_ok=True)
        media = Path(settings.MEDIA_ROOT)
        if media.exists():
            shutil.copytree(media, out / "media", dirs_exist_ok=True)
