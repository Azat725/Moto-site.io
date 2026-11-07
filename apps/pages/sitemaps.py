from django.contrib.sitemaps import Sitemap
from django.urls import reverse

from apps.catalog.models import Motorcycle


class StaticSitemap(Sitemap):
    changefreq = "weekly"

    def items(self):
        return ["pages:home", "pages:catalog", "pages:delivery", "pages:reviews", "pages:about", "pages:contacts",
                "pages:privacy", "pages:consent", "pages:terms", "pages:cookies"]

    def location(self, item):
        return reverse(item)

    def priority(self, item):
        return {"pages:home": 1.0, "pages:catalog": 0.9}.get(item, 0.4)


class MotorcycleSitemap(Sitemap):
    changefreq = "weekly"
    priority = 0.8

    def items(self):
        return Motorcycle.objects.filter(is_published=True)

    def lastmod(self, obj):
        return obj.updated_at


SITEMAPS = {"static": StaticSitemap, "models": MotorcycleSitemap}
