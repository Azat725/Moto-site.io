# IV&AX MOTO: Docker Compose и обновление одной командой

Docker-вариант использует существующий Django-проект. Он заменяет установку Python/Gunicorn/Caddy и
службы `ivax*` на хосте. Выберите один способ развёртывания: не запускайте одновременно старые systemd-службы
и Docker-контейнеры на одной рабочей базе. В этой задаче VPS не разворачивается.

## Что запускается

| Сервис | Назначение |
|---|---|
| `init` | Копия существующей базы и фото → `check --deploy` → миграции → `collectstatic`; затем завершение |
| `web` | Gunicorn, 3 воркера, стандартная Django Admin и публичный сайт |
| `notify` | Существующий `send_notifications --loop --interval 5` |
| `maintenance` | Курс при запуске и каждые 3 часа; бэкап ежедневно в 03:30; политика хранения в 04:15 МСК |
| `caddy` | HTTP/HTTPS, сертификаты, ограничения загрузок, отдача фото и proxy к Django |

`web` запускается только после успешного `init`; остальные службы — после проверки здоровья Django.
Compose дожидается готовности сервисов с `--wait`.
[Порядок запуска Compose](https://docs.docker.com/compose/how-tos/startup-order/).

Python-контейнер работает от UID/GID 10001, корневая файловая система доступна только для чтения.
База, media и остальные изменяемые каталоги подключены томами. Dockerfile включает только код приложения:
локальные `.env`, SQLite, фотографии владельца, `_private`, Git и `.venv` в образ не попадают.
Базовые образы Python и Caddy закреплены digest, Python-зависимости — существующим `requirements.txt`.

## 1. Что нужно на VPS

- Linux VPS в РФ, ориентировочно 2 vCPU / 2 ГБ RAM / 30 ГБ SSD для старта.
- Docker Engine с плагином **Docker Compose ≥ 2.30**, Git, доступ по SSH.
- Подтверждённый домен с A/AAAA на VPS и открытые TCP 80/443; UDP 443 — для HTTP/3.
- Инструкции установки Docker: [Debian](https://docs.docker.com/engine/install/debian/),
  [Ubuntu](https://docs.docker.com/engine/install/ubuntu/). Пакеты ставить из официального репозитория Docker.

Проверить:

```bash
docker version
docker compose version
git --version
```

Порты публикует только Caddy. Gunicorn/SQLite наружу не открываются. При использовании Docker правила
опубликованных портов нужно учитывать в firewall провайдера и Docker: не полагаться только на UFW.
[Docker и firewall](https://docs.docker.com/engine/network/packet-filtering-firewalls/).

## 2. Первый запуск: один раз

Клонировать **согласованный production-выпуск** в `/srv/ivax/app`. По правилам проекта VPS обновляется из `main`;
до согласования и переноса Docker-версии в `main` эти команды на рабочем сервере не выполнять.

```bash
sudo mkdir -p /srv/ivax
sudo git clone --branch main https://github.com/Azat725/Moto-site.io.git /srv/ivax/app
cd /srv/ivax/app
cp .env.docker.example .env
chmod 600 .env
```

Заполнить `.env` редактором. Требуются отдельные случайные `DJANGO_SECRET_KEY` (≥ 50 символов),
`IP_HASH_SALT` (≥ 32), `ADMIN_PATH` (12–80 символов, латиница/цифры/`_`/`-`).
Сгенерировать значения на VPS можно без Python на хосте:

```bash
docker run --rm python:3.13-slim-trixie python -c 'import secrets; print(secrets.token_urlsafe(64)); print(secrets.token_urlsafe(32)); print(secrets.token_urlsafe(18))'
```

Результаты по порядку — ключ Django, соль, путь админки. Не публиковать их и не сохранять в Git.
Остальные обязательные поля:

| Поле | Значение |
|---|---|
| `DJANGO_ALLOWED_HOSTS` | Подтверждённые домены через запятую, без схемы/путей/масок |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | Те же домены с `https://`, без конечного `/` |
| `SITE_DOMAIN` | Подтверждённый основной HTTPS-адрес |
| `CADDY_SITE_ADDRESSES` | Домены для HTTPS через запятую; соответствуют ALLOWED_HOSTS |
| `SITE_NOINDEX` | Оставить `true`, пока владелец явно не разрешит индексацию |
| `COMPOSE_PROJECT_NAME` | Оставить `ivax`: это также префикс постоянных томов |

SMTP/Telegram заполняются по прежним инструкциям; пустые поля выключают соответствующий канал.
`TELEGRAM_INCLUDE_PD=false` сохранить. Значения с `$` в стандартном env-файле Compose заключать в одинарные
кавычки, чтобы избежать интерполяции. `.env` не нужно выполнять через `source`.
[Переменные Compose](https://docs.docker.com/compose/how-tos/environment-variables/variable-interpolation/).

`DATA_DIR`, `MEDIA_ROOT`, `BACKUP_DIR` и параметры доверенного proxy Compose задаёт внутри контейнеров.
Доверяется только конкретный IP Caddy: `172.30.61.2`. Если подсеть конфликтует с сетями VPS/VPN,
изменить **вместе** `DOCKER_SUBNET` и `CADDY_CONTAINER_IP`, сохранив адрес Caddy внутри выбранной подсети.
Отключать VPN или доверять любым proxy не требуется.

Запустить:

```bash
sh deploy/docker/update.sh
```

Первый запуск создаёт пустую production-базу, применяет миграции и собирает статику. Каталог и
пользователи **не создаются автоматически**. На этой новой пустой базе один раз загрузить реальный прайс:

```bash
docker compose --env-file .env exec web python manage.py seed_catalog
docker compose --env-file .env exec web python manage.py update_rate
docker compose --env-file .env exec web python manage.py createsuperuser
```

`seed_catalog` не повторять на действующем каталоге. Пароль production-владельца задаётся интерактивно;
тестовая локальная база не переносится. Заполнить реальные контакты и реквизиты в админке.
Проверить сайт и `https://домен/<ADMIN_PATH>/`, фото, статику, цены, формы и доставку уведомлений.

## 3. Обновление одной командой

После согласованного выпуска в `main`:

```bash
cd /srv/ivax/app && git pull --ff-only && sh deploy/docker/update.sh
```

Внутри скрипта выполняются:

1. Проверка Compose и сборка нового образа. При ошибке сборки работающие службы сохраняются.
2. Остановка Caddy, отправителя, плановых задач и веб-приложения.
3. `docker compose --env-file .env up -d --force-recreate --wait --wait-timeout 240`.
4. `init` делает копию существующих данных, проверяет production, применяет миграции и собирает статику.
5. Запуск Django и зависимых служб, ожидание готовности, вывод `compose ps`.

Обновление сопровождается короткой остановкой сайта. Если резервирование/миграции/проверки завершились
ошибкой, новые службы не запускаются: причина видна в `logs init`. Автоматического отката базы нет.
Не выполняются `down -v`, очистка томов, пересоздание каталога, создание пользователей или сброс данных.
Перед обновлением просмотреть миграции; разрушительные изменения требуют отдельного согласования.

Прямая команда из примера также поддерживается:

```bash
docker compose --env-file .env up -d --build --wait
```

Для обновления существующей SQLite-базы используйте `update.sh`: он останавливает **все** процессы записи
до подготовки базы. Прямой `up` удобен для первого запуска, но не обеспечивает эту остановку старых workers.

## 4. Постоянные данные и копии

| Том | Содержимое |
|---|---|
| `ivax_data` | SQLite, WAL/SHM и файловый кэш |
| `ivax_media` | Фотографии каталога |
| `ivax_backups` | Папки `site-<UTC-время>-<суффикс>`: `db.sqlite3`, `media.tar.gz`, `metadata.json` |
| `ivax_staticfiles` | Пересобираемая статика Django/админки |
| `ivax_caddy_data`, `ivax_caddy_config` | Сертификаты и служебные данные Caddy |

Названия приведены для `COMPOSE_PROJECT_NAME=ivax`. Не меняйте имя проекта и каталог установки во время
обычного обновления: другой проект использует другие тома и выглядит как новая пустая установка.
`docker compose down` сохраняет данные; `docker compose down -v` удаляет тома — для production не использовать.

Ручная копия:

```bash
docker compose --env-file .env exec maintenance python manage.py backup_site
mkdir -p /srv/ivax/backup-export
docker compose --env-file .env cp maintenance:/srv/ivax/backups/. /srv/ivax/backup-export/
chmod -R go-rwx /srv/ivax/backup-export
```

Копии содержат ПДн: сохранять вне VPS в защищённом хранилище РФ. `.env` сохранять отдельно, с доступом
только владельца. Бэкапы не удаляются автоматически: следить за свободным местом и управлять хранением
после проверки внешних копий. Каталоги `.incomplete-*` означают неуспешное резервирование и не являются
готовыми копиями. Старые данные при ошибке не удаляются.

## 5. Диагностика и восстановление

```bash
docker compose --env-file .env ps
docker compose --env-file .env logs --tail 100 init web notify maintenance caddy
docker compose --env-file .env exec web python manage.py check --deploy --fail-level WARNING
docker compose --env-file .env exec web python manage.py showmigrations
docker compose --env-file .env restart notify
docker system df
df -h
```

Не публиковать полный `docker compose config`: вывод может содержать секреты. Для проверки использовать
`docker compose --env-file .env config --quiet`.

При аварии остановить все контейнеры, сохранить текущие тома и выбрать соответствующий комплект кода,
БД и media из проверенного бэкапа. Остановленные контейнеры сохраняются и допускают `docker compose cp`:

```bash
docker compose --env-file .env stop
mkdir -p /srv/ivax/recovery-before-restore
docker compose --env-file .env cp web:/srv/ivax/data/. /srv/ivax/recovery-before-restore/data/
docker compose --env-file .env cp web:/srv/ivax/media/. /srv/ivax/recovery-before-restore/media/
chmod -R go-rwx /srv/ivax/recovery-before-restore
```

Дальнейшее восстановление выполнять после согласования даты и SHA: нужно заменить SQLite вместе с
сопутствующими WAL/SHM, восстановить соответствующие media, UID/GID 10001 и совместимый код. Не распаковывать
архив поверх работающей базы и не запускать произвольный новый код с восстановленной старой схемой.
Проверить `PRAGMA integrity_check` на выбранной копии, затем запустить согласованный выпуск через `update.sh`
и повторить приёмку. Ошибочные миграции и сохранение более новых заявок разбираются отдельно.

## 6. Переезд с существующего systemd-VPS

Это отдельная операция с резервной копией и остановкой `ivax*`, обоих таймеров и Caddy на хосте.
Данные сначала копируются в нужные Docker-тома с UID/GID 10001, сверяются, затем запускается Compose.
На такой базе **не выполнять `seed_catalog`**. Обычный update-скрипт не импортирует хостовую базу сам
и не отключает существующие службы. До покупки/предоставления VPS этот переезд не выполняется.

## 7. Проверка разработки

```bash
python -m pytest tests/integration/test_container_commands.py
python scripts/docker_smoke.py
```

Второй сценарий требует работающего Linux Docker engine. Он создаёт собственный случайный Compose-проект,
проверяет сборку/запуск, production-проверки, публичные страницы, входную форму админки, media и статику,
пересоздание контейнеров с сохранением 15 моделей, изменения настроек и фотографий, целостность копии.
Затем удаляет **только свои** тестовые контейнеры/тома. HTTP и отключение HTTPS-редиректа используются
исключительно в этой одноразовой проверке с доменом `example.test`.
