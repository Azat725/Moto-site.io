"""Страницы сайта на засеянном каталоге: 200, SEO-разметка, запрещённые слова, конфигуратор, редиректы."""
from datetime import date
from decimal import Decimal

import pytest
from django.test import override_settings

from apps.catalog import pricing
from apps.catalog.models import Motorcycle
from apps.catalog.seed_loader import load_seed, seed_catalog
from apps.catalog.services import current_context
from apps.rates.models import Rate
from apps.reviews.models import Review
from tests.factories import make_review
from tests.fixtures.html import inspect

pytestmark = pytest.mark.django_db

SEED_SLUGS = [m["slug"] for m in load_seed()["models"] if m.get("published", True)]
HTML_PAGES = ["/", "/catalog/", "/delivery/", "/reviews/", "/about/", "/contacts/", "/privacy/", "/consent/",
              "/consent-publication/", "/terms/", "/cookies/", "/thanks/", "/preview/home-classic/", "/preview/logo/"]
NOINDEX_PAGES = {"/thanks/", "/preview/home-classic/", "/preview/logo/"}
CANONICAL_OVERRIDES = {"/preview/home-classic/": "/"}  # превью главной ссылается на оригинал
FORBIDDEN = ("maichi", "под заказ", "тест-драйв", "рассрочк", "maichikeji", "18661277768")


@pytest.fixture
def catalog(clock):
    seed_catalog(with_photos=False)
    Rate.objects.create(currency="USD", value=Decimal("81.5000"), effective_date=date(2026, 11, 7),
                        source="cbr_xml", accepted=True)


def _all_html_urls():
    return HTML_PAGES + [f"/moto/{slug}/" for slug in SEED_SLUGS]


def _keys(data) -> list[str]:
    if isinstance(data, dict):
        return [*data.keys(), *(k for v in data.values() for k in _keys(v))]
    if isinstance(data, list):
        return [k for v in data for k in _keys(v)]
    return []


def test_seed_is_not_empty():
    assert len(SEED_SLUGS) >= 1


@pytest.mark.parametrize("path", _all_html_urls())
def test_html_page_renders_with_seo_basics(client, catalog, path):
    response = client.get(path)

    assert response.status_code == 200, path
    assert response["Content-Type"].startswith("text/html")
    html = response.content.decode()
    page = inspect(html)

    assert page.h1_count == 1, f"{path}: h1 = {page.h1_count}"
    assert page.title.strip() and "IV&AX MOTO" in page.title
    assert page.meta.get("description", "").strip(), f"{path}: пустой meta description"
    assert len(page.canonical) == 1 and page.canonical[0].startswith("https://")
    expected_canonical = CANONICAL_OVERRIDES.get(path, path)
    assert page.canonical[0].endswith(expected_canonical), page.canonical
    blocks = page.json_ld()
    assert blocks, f"{path}: нет JSON-LD"
    for block in blocks:
        assert block["@context"] == "https://schema.org" and block["@type"]
    duplicates = {i for i in page.ids if page.ids.count(i) > 1}
    assert not duplicates, f"{path}: повторяющиеся id {duplicates}"


@pytest.mark.parametrize("path", _all_html_urls())
def test_forbidden_words_absent(client, catalog, path):
    html = client.get(path).content.decode().lower()
    found = [word for word in FORBIDDEN if word in html]
    assert not found, f"{path}: {found}"


@pytest.mark.parametrize("path", _all_html_urls())
def test_noindex_only_on_service_pages_when_site_indexable(client, catalog, settings, path):
    settings.SITE_NOINDEX = False

    robots = inspect(client.get(path).content.decode()).meta["robots"]

    if path in NOINDEX_PAGES:
        assert "noindex" in robots, path
    else:
        assert robots.startswith("index"), path


def test_everything_noindex_while_site_closed(client, catalog, settings):
    settings.SITE_NOINDEX = True
    for path in ["/", "/catalog/", f"/moto/{SEED_SLUGS[0]}/"]:
        assert "noindex" in inspect(client.get(path).content.decode()).meta["robots"]


@pytest.mark.parametrize("slug", SEED_SLUGS)
def test_model_page_configurator_data(client, catalog, slug):
    page = inspect(client.get(f"/moto/{slug}/").content.decode())
    raw = page.script_by_id("cfg-data")
    assert raw is not None, "нет #cfg-data"

    import json

    cfg = json.loads(raw)
    assert not [k for k in _keys(cfg) if "usd" in k.lower()], "в браузер не должны уходить цены поставщика"
    assert "markup" not in raw.lower()

    moto = Motorcycle.objects.get(slug=slug)
    ctx = current_context()
    assert ctx.rate == Decimal("81.5000")
    expected = {v.id: pricing.variant_kopecks(v.price_usd, ctx) for v in moto.variants.all()}
    assert {v["id"]: v["kop"] for v in cfg["variants"]} == expected
    assert cfg["step"] == ctx.step
    by_code = {o.option.code: o for o in moto.options.all()}
    for option in cfg["options"]:
        source = by_code[option["code"]]
        want = 0 if source.is_included else pricing.option_kopecks(source.price_usd, ctx)
        assert option["kop"] == want and option["included"] is source.is_included


@pytest.mark.parametrize("slug", SEED_SLUGS[:3])
def test_model_page_product_json_ld(client, catalog, slug):
    blocks = inspect(client.get(f"/moto/{slug}/").content.decode()).json_ld()
    product = next(b for b in blocks if b["@type"] == "Product")
    assert product["sku"] == slug
    if "offers" in product:
        assert product["offers"]["priceCurrency"] == "RUB"
        assert product["offers"]["lowPrice"] <= product["offers"]["highPrice"]


def test_home_and_catalog_list_every_published_model(client, catalog):
    for path in ["/", "/catalog/"]:
        html = client.get(path).content.decode()
        for slug in SEED_SLUGS:
            assert f"/moto/{slug}/" in html, (path, slug)


def test_unpublished_model_404(client, catalog):
    Motorcycle.objects.filter(slug=SEED_SLUGS[0]).update(is_published=False)
    assert client.get(f"/moto/{SEED_SLUGS[0]}/").status_code == 404
    assert client.get("/moto/no-such-model/").status_code == 404


def test_reviews_page_shows_only_approved(client, catalog):
    make_review(display_name="Одобренный", status=Review.Status.APPROVED)
    make_review(display_name="Скрытый", status=Review.Status.PENDING)

    html = client.get("/reviews/").content.decode()

    assert "Одобренный" in html and "Скрытый" not in html


def test_lead_form_carries_signed_token(client, catalog):
    html = client.get(f"/moto/{SEED_SLUGS[0]}/").content.decode()
    assert 'name="form_token"' in html


@override_settings(SITE_MODE="demo", SHOW_SAMPLE_REVIEWS=True)
def test_demo_mode_ribbon_and_sample_reviews(client, catalog):
    html = client.get("/").content.decode()
    assert "demo-ribbon" in html
    assert "Пример отзыва" in html


class TestRobotsAndSitemap:
    def test_robots_closed(self, client, settings):
        settings.SITE_NOINDEX = True
        response = client.get("/robots.txt")
        assert response.status_code == 200
        assert response["Content-Type"].startswith("text/plain")
        assert response.content.decode() == "User-agent: *\nDisallow: /\n"

    def test_robots_open(self, client, settings):
        settings.SITE_NOINDEX = False
        body = client.get("/robots.txt").content.decode()
        assert settings.ADMIN_PATH.strip("/") not in body, "robots.txt не должен раскрывать адрес админки"
        assert "Disallow: /api/" in body and "Disallow: /preview/" in body and "Disallow: /thanks/" in body
        assert f"Sitemap: {settings.SITE_DOMAIN}/sitemap.xml" in body

    def test_sitemap_lists_models_and_static_pages(self, client, catalog):
        response = client.get("/sitemap.xml")

        assert response.status_code == 200
        xml = response.content.decode()
        for slug in SEED_SLUGS:
            assert f"/moto/{slug}/" in xml
        assert "/catalog/" in xml and "/privacy/" in xml
        assert "/preview/" not in xml and "/thanks/" not in xml


class TestLegacyRedirects:
    @pytest.mark.parametrize("old, new", [
        *[pytest.param(old, "/catalog/")
          for old in ("/test-drive.html", "/credit.html", "/catalog.html")],
        ("/bikes/x.html", "/catalog/"), ("/bikes/yamaha-r3.html", "/catalog/"), ("/index.html", "/"),
        ("/about.html", "/about/"), ("/privacy.html", "/privacy/"), ("/cookies.html", "/cookies/"),
    ])
    def test_permanent_redirect(self, client, old, new):
        response = client.get(old)
        assert response.status_code == 301
        assert response["Location"] == new
