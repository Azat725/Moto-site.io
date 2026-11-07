"""Структурированные данные schema.org (JSON-LD) для поисковиков."""
from __future__ import annotations

from urllib.parse import urlsplit

from django.conf import settings
from django.templatetags.static import static
from django.urls import reverse

from apps.catalog.models import SiteSettings

from .content import FAQ


def site_origin() -> str:
    """Схема и хост без пути: reverse() и static() сами добавляют префикс (/Moto-site.io в демо)."""
    parts = urlsplit(settings.SITE_DOMAIN)
    return f"{parts.scheme}://{parts.netloc}"


def _abs(path: str) -> str:
    return site_origin() + path


def dealer(site: SiteSettings) -> dict:
    return {
        "@context": "https://schema.org",
        "@type": "MotorcycleDealer",
        "name": "IV&AX MOTO",
        "url": _abs(reverse("pages:home")),
        "image": _abs(static("assets/og-image.png")),
        "telephone": site.phone_raw,
        "email": site.email,
        "description": "Электромотоциклы в Нижнекамске: каталог, конфигуратор комплектаций, цены по курсу ЦБ РФ.",
        "address": {"@type": "PostalAddress", "addressLocality": "Нижнекамск",
                    "addressRegion": "Республика Татарстан", "addressCountry": "RU", "streetAddress": site.address},
        "areaServed": "RU",
    }


def faq_page() -> dict:
    return {
        "@context": "https://schema.org", "@type": "FAQPage",
        "mainEntity": [{"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": a}}
                       for q, a in FAQ],
    }


def item_list(cards: list[dict]) -> dict:
    return {
        "@context": "https://schema.org", "@type": "ItemList", "name": "Каталог электромотоциклов IV&AX MOTO",
        "itemListElement": [{"@type": "ListItem", "position": i, "name": f"Электромотоцикл {c['moto'].name}",
                             "url": _abs(c["moto"].get_absolute_url())} for i, c in enumerate(cards, start=1)],
    }


def breadcrumbs(items: list[tuple[str, str]]) -> dict:
    full = [("Главная", reverse("pages:home")), *items]
    return {
        "@context": "https://schema.org", "@type": "BreadcrumbList",
        "itemListElement": [{"@type": "ListItem", "position": i, "name": name, "item": _abs(url)}
                            for i, (name, url) in enumerate(full, start=1)],
    }


def product(card: dict) -> dict:
    moto, offer, photo = card["moto"], card["offer"], card["photo"]
    data = {
        "@context": "https://schema.org", "@type": "Product",
        "name": f"Электромотоцикл {moto.name}", "description": moto.short or moto.name,
        "category": "Электромотоциклы", "sku": moto.slug,
        "image": _abs(photo.image.url) if photo else _abs(static("assets/og-image.png")),
        "additionalProperty": [
            {"@type": "PropertyValue", "name": "Мощность", "value": card["power_label"]},
            {"@type": "PropertyValue", "name": "Максимальная скорость", "value": f"{card['max_speed']} км/ч"},
            {"@type": "PropertyValue", "name": "Запас хода", "value": f"до {card['max_range']} км"},
        ],
    }
    if offer.min_price_rub:
        data["offers"] = {"@type": "AggregateOffer", "priceCurrency": "RUB", "lowPrice": offer.min_price_rub,
                          "highPrice": offer.max_price_rub, "offerCount": len(offer.variants),
                          "url": _abs(moto.get_absolute_url())}
    return data
