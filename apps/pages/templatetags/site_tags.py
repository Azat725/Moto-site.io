"""Теги шаблонов: иконки, логотип, форматирование цен, JSON-LD."""
from __future__ import annotations

import json

from django import template
from django.conf import settings
from django.utils.html import format_html
from django.utils.safestring import mark_safe

from ..icons import ICONS, LOGOS

register = template.Library()
NBSP = " "


@register.simple_tag
def icon(name: str, cls: str = ""):
    path = ICONS.get(name, "")
    return format_html(
        '<svg class="ico {}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" '
        'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false">{}</svg>',
        cls, mark_safe(path),
    )


@register.simple_tag
def logo_mark(concept: str = "", cls: str = "logo__mark"):
    svg = LOGOS.get(concept or settings.SITE_LOGO, LOGOS["volt"])
    return mark_safe(svg.replace("<svg ", f'<svg class="{cls}" aria-hidden="true" focusable="false" ', 1))


@register.filter
def rub(value) -> str:
    if value in (None, ""):
        return "по запросу"
    return f"{int(value):,}".replace(",", NBSP) + NBSP + "₽"


@register.filter
def rate_fmt(value) -> str:
    return f"{value:.2f}".replace(".", ",") if value is not None else ""


@register.simple_tag(takes_context=True)
def abs_url(context, path: str = "") -> str:
    from ..seo import site_origin

    request = context.get("request")
    if path:
        return settings.SITE_DOMAIN + path
    return site_origin() + (request.path if request else "/")


@register.simple_tag
def json_script_ld(data: dict):
    payload = json.dumps(data, ensure_ascii=False).replace("<", "\\u003c")
    return mark_safe(f'<script type="application/ld+json">{payload}</script>')


@register.simple_tag
def cfg_json(data: dict):
    payload = json.dumps(data, ensure_ascii=False).replace("<", "\\u003c")
    return mark_safe(f'<script type="application/json" id="cfg-data">{payload}</script>')
