"""Проверка Django и чтения каталога внутри контейнера, без публичного HTTP-порта."""
import os
from urllib.request import Request, urlopen

host = os.environ["DJANGO_ALLOWED_HOSTS"].split(",")[0].strip()
request = Request("http://127.0.0.1:8000/catalog/", headers={"Host": host, "X-Forwarded-Proto": "https"})
with urlopen(request, timeout=5) as response:
    if response.status != 200:
        raise SystemExit(1)
