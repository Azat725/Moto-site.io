"""Отправка публичных форм как application/x-www-form-urlencoded.

Django test Client по умолчанию шлёт dict как multipart/form-data, а PublicUploadGuardMiddleware отвечает на
multipart вне админки 415 — поэтому публичные адреса тестируем так же, как их вызывает браузерный fetch.
"""
from __future__ import annotations

from urllib.parse import urlencode

FORM_CT = "application/x-www-form-urlencoded"
JSON_ACCEPT = {"HTTP_ACCEPT": "application/json"}


def post_form(client, url: str, data: dict, json: bool = True, **extra):
    headers = {**(JSON_ACCEPT if json else {}), **extra}
    return client.post(url, data=urlencode(data, doseq=True), content_type=FORM_CT, **headers)
