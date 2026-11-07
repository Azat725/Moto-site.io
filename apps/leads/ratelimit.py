"""Простое ограничение частоты запросов по хэшу IP (кэш Django)."""
from django.core.cache import cache


def client_ip(request) -> str:
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
