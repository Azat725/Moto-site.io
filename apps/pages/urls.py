from django.contrib.sitemaps.views import sitemap
from django.urls import path, re_path
from django.views.generic import RedirectView

from . import views
from .sitemaps import SITEMAPS

app_name = "pages"


def page(route: str, key: str):
    return path(route, views.static_page, {"page": key}, name=key)


urlpatterns = [
    path("", views.home, name="home"),
    path("catalog/", views.catalog, name="catalog"),
    path("moto/<slug:slug>/", views.model_detail, name="model"),
    path("reviews/", views.reviews_page, name="reviews"),
    page("delivery/", "delivery"),
    page("about/", "about"),
    page("contacts/", "contacts"),
    page("privacy/", "privacy"),
    page("consent/", "consent"),
    page("consent-publication/", "consent_publication"),
    page("terms/", "terms"),
    page("cookies/", "cookies"),
    page("thanks/", "thanks"),
    path("preview/home-classic/", views.home_classic, name="preview_home_classic"),
    page("preview/logo/", "preview_logo"),
    path("robots.txt", views.robots_txt, name="robots"),
    path("sitemap.xml", sitemap, {"sitemaps": SITEMAPS}, name="sitemap"),
    # старые адреса статического сайта
    re_path(r"^bikes/(?P<slug>[a-z0-9-]+)\.html$", RedirectView.as_view(url="/catalog/", permanent=True)),
    re_path(r"^(test-drive|credit|catalog)\.html$", RedirectView.as_view(pattern_name="pages:catalog", permanent=True)),
    re_path(r"^index\.html$", RedirectView.as_view(pattern_name="pages:home", permanent=True)),
    re_path(r"^(?P<page>about|contacts|privacy|consent|terms|cookies)\.html$",
            RedirectView.as_view(url="/%(page)s/", permanent=True), name="legacy_page"),
]
