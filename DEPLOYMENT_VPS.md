# Развёртывание IV&AX MOTO на VPS

Актуально для Django-версии проекта, подготовленной 7 ноября 2026 года. Деплой в этой задаче **не выполнялся**.
Перед установкой убедитесь, что проверенная Django-версия уже согласована и включена в `main`: старый статический
`main` не содержит `manage.py`. На сервер не переносить `data/`, `.env`, `.venv/` и локальных пользователей.

## 1. Фактическая инфраструктура и выбор VPS

| Компонент | Реализация проекта |
|---|---|
| Python | 3.13+; локальная проверка выполнена на 3.14.2 |
| Django | 6.1.3, версии закреплены в `requirements.txt` |
| База | SQLite, WAL, `transaction_mode=IMMEDIATE`, таймаут 20 секунд |
| HTTP | Caddy → Gunicorn `config.wsgi:application` → Django |
| Статика | WhiteNoise, `collectstatic` в `/srv/ivax/app/staticfiles` |
| Фото | `/srv/ivax/media`, Caddy отдаёт `/media/` напрямую |
| Уведомления | `ivax-notify.service`, существующая очередь Outbox в SQLite |
| Планировщик | systemd: `ivax-rate.timer`, `ivax-purge.timer` |
| Кэш | Файловый, `/srv/ivax/data/cache` |
| Docker / ASGI / WebSocket / Redis / Celery | Не используются, устанавливать их не требуется |

Для старта с небольшой посещаемостью: минимум 1 vCPU, 1 ГБ RAM, 20 ГБ SSD; рекомендуется 2 vCPU, 2 ГБ RAM,
30 ГБ SSD и отдельное место для резервных копий. Это оценка для текущих 15 моделей и трёх sync-воркеров Gunicorn,
а не результат нагрузочного теста. При росте нагрузки оцените память, длительность запросов и блокировки SQLite.
VPS и резервные копии с заявками разместить в РФ по правилам проекта.

Целевая ОС этой инструкции — **Debian 13 amd64**, где системный Python 3.13 подходит проекту.
Проверка Python обязательна; не подменяйте системный Python и не устанавливайте неподтверждённые зависимости.
Источники: [Debian 13](https://www.debian.org/releases/trixie/release-notes/whats-new.en.html),
[контрольный список Django](https://docs.djangoproject.com/en/6.1/howto/deployment/checklist/).
Установку Linux-служб, TLS и реальную доставку SMTP/Telegram нужно будет проверить на приобретённом VPS.

## 2. SSH и первоначальная безопасность

Подставьте выданный провайдером IP; `VPS_IP` ниже — обозначение, не готовый адрес.

```bash
ssh root@VPS_IP
apt update
apt upgrade
apt install -y sudo openssh-server ufw unattended-upgrades
adduser ivaxops
usermod -aG sudo ivaxops
install -d -m 700 -o ivaxops -g ivaxops /home/ivaxops/.ssh
nano /home/ivaxops/.ssh/authorized_keys
chown ivaxops:ivaxops /home/ivaxops/.ssh/authorized_keys
chmod 600 /home/ivaxops/.ssh/authorized_keys
```

В `authorized_keys` вставить **публичный** SSH-ключ своего компьютера. В другом терминале проверить
`ssh ivaxops@VPS_IP` и `sudo -v`. Только после успешной проверки входа по ключу:

```bash
sudo nano /etc/ssh/sshd_config.d/60-ivax.conf
```

Содержимое (при стандартном порте SSH 22):

```text
PermitRootLogin no
PasswordAuthentication no
PubkeyAuthentication yes
```

```bash
sudo sshd -t
sudo systemctl reload ssh
sudo ufw allow 22/tcp
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw enable
sudo ufw status
sudo timedatectl set-timezone Europe/Moscow
sudo systemctl enable --now unattended-upgrades
```

Порт 8000 не открывать: Gunicorn слушает только loopback. У провайдера также разрешить TCP 22/80/443.
Для нестандартного SSH-порта сначала разрешить именно его, затем включать firewall.

## 3. Системные пакеты и служебный пользователь

```bash
sudo apt install -y python3 python3-venv python3-pip git sqlite3 caddy ca-certificates curl cron
python3 --version
sudo adduser --system --group --home /srv/ivax --shell /bin/bash ivax
sudo mkdir -p /srv/ivax/app /srv/ivax/data /srv/ivax/media /srv/ivax/backups
sudo chown -R ivax:ivax /srv/ivax
sudo chmod 750 /srv/ivax /srv/ivax/app /srv/ivax/media
sudo chmod 700 /srv/ivax/data /srv/ivax/backups
sudo usermod -aG ivax caddy
```

Отдельный сервер БД не нужен: SQLite создаст базу миграциями. У Python проверить поддержку SQLite и WebP:

```bash
python3 -c "import sqlite3; print(sqlite3.sqlite_version)"
```

На amd64 устанавливаются wheel-пакеты из закреплённых зависимостей. Если wheel недоступен, остановитесь
и проверьте совместимость ОС, архитектуры и Python; не обновляйте версии произвольно.

## 4. Код и виртуальное окружение

```bash
sudo -iu ivax
umask 027
git clone --branch main https://github.com/Azat725/Moto-site.io.git /srv/ivax/app
cd /srv/ivax/app
test -f manage.py
git status --short
git rev-parse HEAD
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m pip check
.venv/bin/python -c "import django; from PIL import features; print(django.get_version()); print(features.check('webp'))"
```

`manage.py` должен существовать, дерево — быть чистым, версия Django — 6.1.3, WebP — `True`.
Сверить SHA с согласованным выпуском и зелёным CI. Здесь и далее команды `.venv/bin/...` выполняются
пользователем `ivax` из `/srv/ivax/app`; команды `sudo` — пользователем `ivaxops` в отдельной SSH-сессии.

## 5. Переменные окружения

```bash
cp .env.example .env
chmod 600 .env
.venv/bin/python -c "import secrets; print(secrets.token_urlsafe(64))"
.venv/bin/python -c "import secrets; print(secrets.token_urlsafe(32))"
.venv/bin/python -c "import secrets; print(secrets.token_urlsafe(18))"
nano .env
```

Три результата — соответственно `DJANGO_SECRET_KEY`, `IP_HASH_SALT`, `ADMIN_PATH`. Хранить в менеджере
паролей и `.env`, не в Git, сообщениях о деплое или журналах. Результаты нельзя переиспользовать с локальной машины.

| Переменная | Что заполнить |
|---|---|
| `DJANGO_SECRET_KEY` | Случайное значение ≥ 50 символов |
| `IP_HASH_SALT` | Отдельное случайное значение ≥ 32 символов |
| `ADMIN_PATH` | Случайная строка 12–80 символов: латиница, цифры, `_`, `-`; завершающий `/` необязателен |
| `DJANGO_ALLOWED_HOSTS` | Подтверждённые домены через запятую, без схемы, пути и `*` |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | Те же домены с `https://`, без завершающего `/` |
| `SITE_DOMAIN` | Подтверждённый основной HTTPS-адрес; менять домен только по указанию владельца |
| `SITE_NOINDEX` | Оставить `true`, пока владелец явно не разрешит индексацию |
| `DATA_DIR` | `/srv/ivax/data` |
| `MEDIA_ROOT` | `/srv/ivax/media` |
| `TRUSTED_PROXY` | `true` |
| `TRUSTED_PROXY_IPS` | `127.0.0.1,::1` |
| `LEAD_NOTIFY_EMAILS` | Адреса менеджеров; пусто — уведомления e-mail выключены |
| `EMAIL_HOST`, `EMAIL_PORT` | SMTP российского провайдера, например порт 465 для SSL |
| `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD` | Учётная запись SMTP и отдельный пароль приложения |
| `EMAIL_USE_SSL`, `EMAIL_USE_TLS` | Для 465: `true`, `false`; для STARTTLS 587: `false`, `true` |
| `DEFAULT_FROM_EMAIL` | Отправитель, соответствующий почтовому ящику |
| `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` | Необязательные; пусто — Telegram выключен |
| `TELEGRAM_INCLUDE_PD` | Оставить `false` |
| `LEAD_RETENTION_DAYS` | Срок хранения заявок по согласованной политике; по умолчанию 1095 |

`DEFAULT_FROM_EMAIL` может содержать пробелы, `&` и `<...>`. **Не выполнять `source .env`**:
файл читают Django и systemd, это не shell-скрипт. Формат `КЛЮЧ=значение`, без `export`.
`DJANGO_SETTINGS_MODULE` для ручных команд задаётся отдельно:

```bash
export DJANGO_SETTINGS_MODULE=config.settings.prod
```

В новой SSH-сессии повторять этот `export`. Службы уже задают его в unit-файлах.
Production принудительно использует `DEBUG=False`, `SITE_MODE=live`, `SHOW_SAMPLE_REVIEWS=False`.
HTTPS-редирект, secure-cookie, HSTS и CSP включены. Не отключать их для обхода ошибки настройки.

## 6. База, статика, начальный каталог и владелец

```bash
.venv/bin/python manage.py check --deploy --fail-level WARNING
.venv/bin/python manage.py migrate --plan
.venv/bin/python manage.py migrate --noinput
.venv/bin/python manage.py makemigrations --check --dry-run
.venv/bin/python manage.py collectstatic --noinput
.venv/bin/python manage.py seed_catalog
.venv/bin/python manage.py update_rate
.venv/bin/python manage.py createsuperuser
```

`seed_catalog` запускать **один раз на новой пустой базе**: это реальные исходные 15 моделей из прайса,
опции, цвета и фотографии с сохранённым водяным знаком. На существующем каталоге команда перезапишет изменения
владельца. При обновлениях её не запускать. Не переносить локальную SQLite-базу: production-пользователь
создаётся интерактивно, с отдельным паролем (≥ 12 символов); пароль хранится хешем scrypt.
`create_local_admin` на production запрещён программно.

Если курс не удалось получить, проверить доступ к источникам и повторить `update_rate`; не считать запасной
курс подтверждённым. В админке доступен явный ручной режим с обязательным значением курса.
Юридические реквизиты и контакты заполнить реальными данными владельца, тексты документов согласовать отдельно.

## 7. Gunicorn, отправитель и таймеры

Из сессии `ivaxops`:

```bash
sudo cp /srv/ivax/app/deploy/ivax*.service /srv/ivax/app/deploy/ivax*.timer /etc/systemd/system/
sudo systemd-analyze verify /etc/systemd/system/ivax*.service /etc/systemd/system/ivax*.timer
sudo systemctl daemon-reload
sudo systemctl enable --now ivax.service ivax-notify.service ivax-rate.timer ivax-purge.timer
sudo systemctl status ivax.service ivax-notify.service --no-pager
systemctl list-timers 'ivax*'
```

`ivax.service` запускает `.venv/bin/gunicorn config.wsgi:application` на `127.0.0.1:8000`, 3 воркера.
`ivax-notify` обрабатывает Outbox каждые 5 секунд, `ivax-rate` обновляет курс каждые 3 часа,
`ivax-purge` выполняет существующую политику хранения ежедневно в 04:15 по времени сервера.
Очистку активировать только с согласованным сроком хранения. Юниты запускаются от `ivax`, запись разрешена
только в каталоги данных и фото. Никакие секреты не нужно вписывать в unit-файлы.

## 8. Домен, Caddy и HTTPS

После подтверждения домена создать A-записи основного домена и `www` на IP VPS. AAAA добавлять только
при настроенном IPv6; ошибочная AAAA мешает выдаче сертификата. Проверить DNS с внешнего компьютера.

```bash
sudo cp /srv/ivax/app/deploy/Caddyfile.example /etc/caddy/Caddyfile
sudo nano /etc/caddy/Caddyfile
```

Заменить домены на согласованные (сейчас пример содержит `ivax-moto.ru, www.ivax-moto.ru`). В **обоих**
вхождениях `/ВАШ-ПУТЬ-АДМИНКИ/*` подставить `/<ADMIN_PATH-без-завершающего-слэша>/*` из `.env`.
Это нужно для загрузки фото и импорта: 12 МБ в админке, 64 КБ на публичных адресах.
Не вставлять значение секрета в общую документацию или команду, попадающую в shell history.

```bash
sudo caddy validate --config /etc/caddy/Caddyfile
sudo systemctl restart caddy
sudo systemctl status caddy --no-pager
```

Caddy получает и продлевает TLS автоматически. Nginx и отдельный certbot не нужны. `/media/*` обслуживается
в отдельном `handle_path`; остальные запросы — в fallback `handle` с `reverse_proxy`. Это исключает
попадание запросов к фото в Django. WhiteNoise отдаёт собранную статику, включая CSS/JS админки.
[Маршрутизация Caddy](https://caddyserver.com/docs/caddyfile/directives/handle),
[автоматический HTTPS](https://caddyserver.com/docs/automatic-https).

## 9. Приёмка на сервере

1. HTTP перенаправляет на HTTPS; сертификат действителен, `/` и `/catalog/` открываются.
2. `robots.txt` содержит `Disallow: /`, индексация остаётся закрытой.
3. Админка по фактическому `ADMIN_PATH`: вход новым production-владельцем, загрузка CSS/JS без 404 и ошибок CSP.
4. Открыть списки каталога, опций, цветов, настроек, курсов, заявок, уведомлений и отзывов.
5. Проверить цену существующего варианта и конфигуратор; не менять рабочие цены только ради проверки.
6. Загрузить разрешённое фото, проверить `/media/...` по HTTPS и после перезапуска служб.
7. Сотруднику создать отдельную staff-запись с минимальными permissions по `docs/admin-guide.md`.
8. Без staff-входа админка недоступна; сотрудник без разрешений не видит чужие разделы и действия.
9. Проверить формы: пустая отправка → ошибки; без согласия отправка блокируется; cookie-выбор сохраняется.
10. После согласования отправить собственную проверочную заявку, убедиться в сохранении, совпадении цены
    и доставке через реальный SMTP/Telegram. Production-очередь и тестовый SMTP не проверялись локально.
11. Проверить модерацию только настоящих отзывов; не публиковать выдуманные отзывы для проверки.
12. Просмотреть сайт на 375/768/1280 px, с выключенным JS и reduced motion; проверить консоль и сеть.

Уведомления отправляет только Outbox-worker. Действие «Повторить отправку сейчас» перепланирует очередь,
не отправляет сообщения в HTTP-запросе и не трогает уже отправляемые/отправленные записи.

## 10. Резервные копии

`deploy/backup.sh`: SQLite `.backup` (поддерживает WAL) + архив `media/`; срок хранения 30 дней.
Скрипт не сохраняет секреты `.env`, TLS и конфигурацию Caddy: их хранить отдельно, с ограниченным доступом.

```bash
sudo -iu ivax
cd /srv/ivax/app
/bin/sh deploy/backup.sh
exit
sudo systemctl enable --now cron
sudo crontab -u ivax -e
```

Строка cron:

```cron
30 3 * * * /bin/sh /srv/ivax/app/deploy/backup.sh
```

Копировать бэкапы на отдельное защищённое хранилище в РФ; проверять наличие и свободный диск.
Периодически восстанавливать на отдельной тестовой машине и проверять `PRAGMA integrity_check` и наличие фото.
Набор для восстановления: SHA кода, соответствующая БД и media, `.env`, `/etc/caddy/Caddyfile` и unit-файлы.
Нельзя копировать одну работающую `db.sqlite3` обычным `cp` в режиме WAL.

## 11. Безопасное обновление

Только согласованный `main` с зелёным CI, проверенными E2E и просмотренным планом миграций.
Сначала сделать бэкап и сохранить SHA текущего выпуска. На время замены кода/миграций остановить **всех**
писателей БД: сайт, отправитель и оба таймера с возможными активными oneshot-службами.

```bash
sudo systemctl stop ivax-rate.timer ivax-purge.timer
sudo systemctl stop ivax.service ivax-notify.service ivax-rate.service ivax-purge.service
sudo -iu ivax
cd /srv/ivax/app
export DJANGO_SETTINGS_MODULE=config.settings.prod
git status --short
git rev-parse HEAD
/bin/sh deploy/backup.sh
git fetch origin
git checkout main
git pull --ff-only
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python manage.py migrate --plan
.venv/bin/python manage.py migrate --noinput
.venv/bin/python manage.py collectstatic --noinput
.venv/bin/python manage.py check --deploy --fail-level WARNING
exit
sudo systemctl start ivax.service ivax-notify.service ivax-rate.timer ivax-purge.timer
```

При грязном дереве или ошибке любого шага не продолжать автоматически. Сначала устранить причину либо выполнить
откат из следующего раздела. `seed_catalog`, `create_local_admin` и локальную базу при обновлении не использовать.
Если изменились unit-файлы — повторить их установку и `daemon-reload`. Caddyfile обновлять с сохранением
реальных доменов и пути админки, затем `caddy validate` и `systemctl reload caddy`. Сверить новые переменные
с `.env.example`; после изменения `.env` перезапустить сайт и отправитель. Повторить приёмку.

## 12. Восстановление и откат

Действия ниже выполняются администратором при реальной аварии после выбора проверенного бэкапа. Не запускать
их вслепую. Сначала остановить все службы/таймеры, как в разделе 11, и сделать отдельную копию аварийных данных.

```bash
sudo -iu ivax
cd /srv/ivax/app
umask 077
recovery_dir="/srv/ivax/backups/recovery-$(date +%Y%m%d-%H%M%S)"
mkdir -p "$recovery_dir"
cp -a /srv/ivax/data "$recovery_dir/data"
cp -a /srv/ivax/media "$recovery_dir/media"
read -r -p 'Дата выбранного бэкапа ГГГГММДД: ' backup_date
printf '%s\n' "$backup_date" | grep -Eq '^[0-9]{8}$'
test -f "/srv/ivax/backups/db-$backup_date.sqlite3"
test -f "/srv/ivax/backups/media-$backup_date.tar.gz"
sqlite3 "/srv/ivax/backups/db-$backup_date.sqlite3" 'PRAGMA integrity_check;'
```

Проверка должна вернуть `ok`; если нет — выбрать другую копию. После проверки:

```bash
mv /srv/ivax/data/db.sqlite3 "$recovery_dir/original-db.sqlite3"
test ! -f /srv/ivax/data/db.sqlite3-wal || mv /srv/ivax/data/db.sqlite3-wal "$recovery_dir/"
test ! -f /srv/ivax/data/db.sqlite3-shm || mv /srv/ivax/data/db.sqlite3-shm "$recovery_dir/"
cp "/srv/ivax/backups/db-$backup_date.sqlite3" /srv/ivax/data/db.sqlite3
mv /srv/ivax/media "$recovery_dir/original-media"
tar -xzf "/srv/ivax/backups/media-$backup_date.tar.gz" -C /srv/ivax
read -r -p 'Согласованный SHA кода для этой копии: ' release_sha
git checkout --detach "$release_sha"
.venv/bin/python -m pip install -r requirements.txt
export DJANGO_SETTINGS_MODULE=config.settings.prod
.venv/bin/python manage.py collectstatic --noinput
.venv/bin/python manage.py check --deploy --fail-level WARNING
.venv/bin/python manage.py showmigrations
exit
sudo systemctl start ivax.service ivax-notify.service ivax-rate.timer ivax-purge.timer
```

Не запускать новые миграции поверх восстановленной БД без проверки совместимости с выбранным SHA.
Восстановление более старой БД откатит и заявки после даты бэкапа: согласовать потерю данных с владельцем,
использовать сохранённую аварийную копию для анализа. Повторить приёмку. Для последующего обновления вернуться
к согласованной ветке `main` только после подготовки совместимого выпуска.

## 13. Диагностика

```bash
sudo systemctl status ivax ivax-notify caddy --no-pager
sudo journalctl -u ivax -u ivax-notify -u caddy --since '30 minutes ago' --no-pager
sudo journalctl -u ivax-rate -u ivax-purge -n 50 --no-pager
systemctl list-timers 'ivax*'
sudo ss -lntp
df -h /srv
free -m
```

В сессии `ivax`, из `/srv/ivax/app`, с `DJANGO_SETTINGS_MODULE=config.settings.prod`:

```bash
.venv/bin/python manage.py check --deploy --fail-level WARNING
.venv/bin/python manage.py showmigrations
sqlite3 /srv/ivax/data/db.sqlite3 'PRAGMA integrity_check;'
```

Админка: «Настройки сайта» → курс и его дата; «Уведомления (очередь)» → ожидание, ошибки, попытки.
Для разблокировки владельца использовать `manage.py axes_reset_username` по инструкции команды `--help`,
не отключая Axes. Логи journald закрыть от посторонних; не включать DEBUG, не публиковать ПДн и секреты.

## 14. Что потребуется от владельца

IP и ОС VPS, способ SSH-доступа по ключу, подтверждение размещения в РФ; домен и доступ к DNS;
согласованный SHA/ветка выпуска; SMTP российского провайдера и адреса менеджеров; при необходимости бот и чат
Telegram; реальные контакты и реквизиты, утверждённые юридические тексты и фото с правом публикации;
место бэкапов в РФ и срок хранения. Секреты передавать защищённым способом, в документацию их не записывать.

Включение индексации, публикация/слияние в `main` и сам деплой требуют отдельного указания владельца.
