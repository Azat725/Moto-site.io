"""Проверить Docker на собственной одноразовой базе: первый запуск → обновление → сохранность данных."""
import json
import os
from pathlib import Path
import secrets
import subprocess
import tempfile
from urllib.error import HTTPError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]


def run(args, *, capture=False, env=None):
    result = subprocess.run(args, cwd=ROOT, check=True, text=True, capture_output=capture, timeout=1200, env=env)
    return result.stdout.strip() if capture else ""


def main():
    project = "ivax-smoke-" + secrets.token_hex(4)
    with tempfile.TemporaryDirectory(prefix="ivax-docker-smoke-") as temporary:
        env_file = Path(temporary) / ".env"
        values = {
            "IVAX_ENV_FILE": str(env_file), "COMPOSE_PROJECT_NAME": project, "IVAX_IMAGE_TAG": project,
            "COMPOSE_FILE": "compose.yaml" + os.pathsep + "deploy/docker/compose.smoke.yaml",
            "DJANGO_SECRET_KEY": secrets.token_urlsafe(64), "IP_HASH_SALT": secrets.token_urlsafe(32),
            "ADMIN_PATH": "smoke-only-admin/", "DJANGO_ALLOWED_HOSTS": "example.test",
            "DJANGO_CSRF_TRUSTED_ORIGINS": "https://example.test", "SITE_DOMAIN": "https://example.test",
            "CADDY_SITE_ADDRESSES": "http://example.test", "SITE_NOINDEX": "true",
            "SECURE_SSL_REDIRECT": "false", "RATE_SOURCES": "", "TELEGRAM_BOT_TOKEN": "",
            "TELEGRAM_CHAT_ID": "", "LEAD_NOTIFY_EMAILS": "", "DOCKER_SUBNET": "172.30.251.0/24",
            "CADDY_CONTAINER_IP": "172.30.251.2",
        }
        env_file.write_text("\n".join(f"{k}={v}" for k, v in values.items()) + "\n", encoding="utf-8")
        env_file.chmod(0o600)
        process_env = os.environ | values
        compose = ["docker", "compose", "--project-name", project, "--env-file", str(env_file)]
        def command(*args, capture=False):
            return run([*compose, *args], capture=capture, env=process_env)
        def python(service, code):
            return command("exec", "-T", service, "python", "-c", code, capture=True)
        def get(path):
            address = command("port", "caddy", "80", capture=True)
            request = Request(f"http://{address}{path}", headers={"Host": "example.test"})
            with urlopen(request, timeout=15) as response:
                return response.read(), response.headers
        try:
            command("config", "--quiet")
            command("build", "--pull")
            command("up", "-d", "--wait", "--wait-timeout", "240")
            code = "import django; django.setup(); from apps.catalog.models import Motorcycle; print(Motorcycle.objects.count())"
            assert python("web", code) == "0", "Каталог не должен засеиваться автоматически"
            assert python("web", "import os; print(os.getuid())") == "10001"
            command("exec", "-T", "web", "python", "manage.py", "seed_catalog")
            marker = ("import django; django.setup(); from apps.catalog.models import SiteSettings; "
                      "s=SiteSettings.load(); s.markup_rub=123456; s.save()")
            python("web", marker)
            photo_code = ("import django; django.setup(); from apps.catalog.models import Photo; "
                          "print(Photo.objects.first().image.url)")
            photo_url = python("web", photo_code)
            photo, _ = get(photo_url)
            assert photo
            page, headers = get("/catalog/")
            assert "IV&AX" in page.decode() and headers["Content-Security-Policy"]
            login, _ = get("/smoke-only-admin/login/")
            assert b"csrfmiddlewaretoken" in login
            static, _ = get("/static/admin/css/base.css")
            assert static
            for private in ("/.env", "/data/db.sqlite3"):
                try:
                    get(private)
                except HTTPError as exc:
                    assert exc.code == 404
                else:
                    raise AssertionError("Приватный путь доступен по HTTP")
            old_id = command("ps", "-q", "web", capture=True)
            run(["sh", "deploy/docker/update.sh", str(env_file)], env=process_env)
            assert old_id != command("ps", "-q", "web", capture=True)
            assert python("web", code) == "15"
            check = ("import django; django.setup(); from apps.catalog.models import SiteSettings; "
                     "print(SiteSettings.load().markup_rub)")
            assert python("web", check) == "123456"
            assert get(photo_url)[0] == photo
            backup = ("from pathlib import Path; import sqlite3; "
                      "p=next(Path('/srv/ivax/backups').glob('site-*/db.sqlite3')); "
                      "db=sqlite3.connect(p); "
                      "assert db.execute('SELECT markup_rub FROM catalog_sitesettings').fetchone()[0]==123456; "
                      "assert db.execute('PRAGMA integrity_check').fetchone()[0]=='ok'; db.close()")
            python("maintenance", backup)
            print(json.dumps({"docker_smoke": "passed", "models_preserved": 15,
                              "media_preserved": True, "backup_verified": True}))
        finally:
            # Имя сгенерировано этим запуском; production-тома и другие проекты не затрагиваются.
            command("down", "--volumes", "--remove-orphans")


if __name__ == "__main__":
    main()
