"""IP посетителя и ограничение частоты заявок/отзывов (счёт по БД — работает с несколькими воркерами)."""
from __future__ import annotations

import ipaddress
from datetime import timedelta

from django.conf import settings
from django.utils import timezone


def client_ip(request) -> str:
    """IP посетителя. Заголовку X-Real-IP верим, только если запрос пришёл от нашего прокси (Caddy)."""
    remote = request.META.get("REMOTE_ADDR", "")
    if settings.TRUSTED_PROXY and remote in settings.TRUSTED_PROXY_IPS:
        real = request.META.get("HTTP_X_REAL_IP", "").strip()
        if real:
            return real
    return remote


def limit_key(ip: str) -> str:
    """Для IPv6 считаем всю сеть /64 (у одного абонента их миллиарды адресов)."""
    try:
        address = ipaddress.ip_address(ip)
    except ValueError:
        return ip
    if address.version == 6:
        return str(ipaddress.ip_network(f"{ip}/64", strict=False))
    return ip


def over_limit(queryset, limit: int, window_seconds: int) -> bool:
    """True, если за окно уже было limit или больше записей (queryset отфильтрован по ip_hash)."""
    since = timezone.now() - timedelta(seconds=window_seconds)
    return queryset.filter(created_at__gte=since).count() >= limit
