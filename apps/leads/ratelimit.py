"""Ограничение частоты запросов по хэшу IP (кэш Django: на сервере — файловый, общий для всех воркеров)."""
from django.conf import settings
from django.core.cache import cache


def client_ip(request) -> str:
    """IP посетителя. За обратным прокси (Caddy/nginx) берём заголовок, который выставляет сам прокси."""
    if settings.TRUSTED_PROXY:
        forwarded = request.META.get("HTTP_X_REAL_IP") or request.META.get("HTTP_X_FORWARDED_FOR", "").split(",")[0]
        if forwarded.strip():
            return forwarded.strip()
    return request.META.get("REMOTE_ADDR", "")


def hit(key: str, limit: int, window_seconds: int) -> bool:
    """Регистрирует запрос. Возвращает False, если лимит превышен."""
    cache_key = f"rl:{key}"
    if cache.add(cache_key, 1, window_seconds):
        return True
    try:
        count = cache.incr(cache_key)
    except ValueError:
        cache.set(cache_key, 1, window_seconds)
        return True
    return count <= limit
