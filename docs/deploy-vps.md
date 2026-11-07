# Установка и обновление на VPS

Полный актуальный маршрут установки, безопасного обновления и восстановления —
[DEPLOYMENT_VPS.md](../DEPLOYMENT_VPS.md). Начните с него; сервер в рамках подготовки не разворачивался.

**Обновлено:** 2026-11-07 · **Файлы:** `deploy/ivax.service`, `deploy/ivax-notify.service`, `deploy/ivax-rate.service`,
`deploy/ivax-rate.timer`, `deploy/ivax-purge.service`, `deploy/ivax-purge.timer`, `deploy/Caddyfile.example`,
`deploy/backup.sh`, `.env.example`, `config/settings/prod.py`

Рабочий сайт (live) рассчитан на VPS: Caddy (HTTPS) → gunicorn → Django, база SQLite. Статическое демо на
GitHub Pages — отдельно, см. [architecture.md](architecture.md#7-режимы-live-и-demo).

## 0. Что нужно заранее

- **VPS в России.** Сайт хранит персональные данные граждан РФ (имя, телефон) — по ч. 5 ст. 18 152-ФЗ база
  должна находиться на серверах в РФ. Достаточно 1 vCPU, 1–2 ГБ RAM, 20 ГБ диска.
- **ОС с Python 3.13+** (например, Debian 13; проверьте `python3 --version`).
- **Домен** с A-записью (и AAAA, если есть IPv6) на IP сервера, `www` — тоже. Открыты порты 22, 80, 443.
- Почтовый ящик у **российского** провайдера для отправки уведомлений (раздел 9) и Telegram-бот (раздел 8).

## 1. Пакеты, пользователь, каталоги

```bash
sudo apt update && sudo apt install -y python3 python3-venv git sqlite3 caddy
sudo adduser --system --group --home /srv/ivax --shell /bin/bash ivax
sudo mkdir -p /srv/ivax/app /srv/ivax/data /srv/ivax/media /srv/ivax/backups
sudo chown -R ivax:ivax /srv/ivax
sudo chmod 750 /srv/ivax /srv/ivax/app /srv/ivax/media
sudo chmod 700 /srv/ivax/data /srv/ivax/backups
sudo usermod -aG ivax caddy        # Caddy отдаёт фото из /srv/ivax/media
```

| Каталог | Что там |
|---------|---------|
| `/srv/ivax/app` | код из git, `.venv`, `.env`, `staticfiles/` |
| `/srv/ivax/data` | `db.sqlite3` (+ `-wal`, `-shm`), `cache/` (лимиты); доступ только у `ivax` |
| `/srv/ivax/media` | загруженные фото (`bikes/<slug>/…webp`) |
| `/srv/ivax/backups` | резервные копии (`backup.sh`) |

## 2. Код и окружение Python

```bash
sudo -iu ivax
git clone https://github.com/Azat725/Moto-site.io.git /srv/ivax/app
cd /srv/ivax/app && git checkout main
python3 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -r requirements.txt
```

На сервере ставится только `requirements.txt` (без тестовых пакетов). Устанавливается **только ветка `main`**.

## 3. Файл `.env`

```bash
cp .env.example .env && chmod 600 .env
python3 -c "import secrets; print(secrets.token_urlsafe(64))"   # → DJANGO_SECRET_KEY
python3 -c "import secrets; print(secrets.token_urlsafe(32))"   # → IP_HASH_SALT
python3 -c "import secrets; print(secrets.token_urlsafe(12))"   # → ADMIN_PATH
nano .env
```

Файл читают systemd (`EnvironmentFile`) и сам Django (`config/env.py`). Формат — `КЛЮЧ=значение`, без кавычек
и `export`. **Не выполняйте `source .env`** в shell: символы `&` и `<` в `DEFAULT_FROM_EMAIL` сломают команду.
`.env` никогда не коммитится и не пересылается в открытом виде.

### Переменные из `.env.example`

| Переменная | Значение |
|------------|----------|
| `DJANGO_SECRET_KEY` | **Обязательно**, случайная строка не короче 50 символов. Без неё `prod.py` не запустится |
| `DJANGO_ALLOWED_HOSTS` | Домены сайта через запятую: `ivax-moto.ru,www.ivax-moto.ru` |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | Те же домены со схемой: `https://ivax-moto.ru,https://www.ivax-moto.ru` |
| `SITE_DOMAIN` | Основной адрес без `/` в конце. Используется в canonical, sitemap, JSON-LD, ссылке из Telegram |
| `SITE_NOINDEX` | `true` — сайт закрыт от поисковиков (`robots.txt` и meta robots). **Меняет на `false` только владелец** при запуске |
| `SITE_LOGO` | Вариант логотипа: `volt`, `horns` или `fang` (сравнение — `/preview/logo/`) |
| `ADMIN_PATH` | **Обязательно**, случайная строка — адрес админки `https://домен/<ADMIN_PATH>/`. Значения `manage-ivax`, `admin` и пустое `prod.py` не принимает |
| `DATA_DIR` | `/srv/ivax/data` — база и кэш |
| `MEDIA_ROOT` | `/srv/ivax/media` — фото |
| `TRUSTED_PROXY` | `true` — сайт за Caddy, IP посетителя берётся из `X-Real-IP` (нужно для лимитов и защиты входа) |
| `TRUSTED_PROXY_IPS` | Адреса прокси, которым верим: `127.0.0.1,::1` |
| `IP_HASH_SALT` | **Обязательно**, случайная строка не короче 32 символов. В базе хранится не IP, а его хэш с этой солью |
| `TELEGRAM_BOT_TOKEN` · `TELEGRAM_CHAT_ID` | Бот и чат менеджеров (раздел 8). Пусто — Telegram выключен |
| `TELEGRAM_API_BASE` | `https://api.telegram.org` (можно указать свой прокси-адрес API) |
| `TELEGRAM_INCLUDE_PD` | `false` — в Telegram без имени и телефона. `true` — трансграничная передача ПДн, только после решения юриста и уведомления РКН |
| `LEAD_NOTIFY_EMAILS` | Адреса менеджеров для писем о заявках, через запятую. Пусто — письма не отправляются |
| `EMAIL_HOST` · `EMAIL_PORT` · `EMAIL_USE_SSL` | SMTP провайдера, например `smtp.yandex.ru`, `465`, `true` |
| `EMAIL_HOST_USER` · `EMAIL_HOST_PASSWORD` | Логин ящика и пароль приложения |
| `DEFAULT_FROM_EMAIL` | Отправитель, должен совпадать с ящиком: `IV&AX MOTO <noreply@ivax-moto.ru>` |
| `LEAD_RETENTION_DAYS` | Срок хранения ПДн в заявках, дней (1095 = 3 года), затем обезличивание |

### Необязательные переменные (значения по умолчанию в `config/settings/base.py`, `prod.py`)

| Переменная | По умолчанию | Назначение |
|------------|--------------|------------|
| `EMAIL_USE_TLS` | `false` | Для порта 587 (STARTTLS) — `true` вместе с `EMAIL_USE_SSL=false` |
| `LOG_LEVEL` | `INFO` | Уровень логов в journald |
| `CONSENT_VERSION` | `2026-11-07` | Версия текста согласия; меняйте при изменении документа — сохраняется в каждой заявке |
| `LEAD_RATE_LIMIT_COUNT` / `_SECONDS` | `5` / `600` | Заявок с одного IP за окно |
| `REVIEW_RATE_LIMIT_COUNT` / `_SECONDS` | `3` / `86400` | Отзывов с одного IP за окно |
| `LEAD_MIN_FILL_SECONDS` | `3` | Форма, отправленная быстрее, считается спамом |
| `RATE_SOURCES` | `cbr_xml,cbr_json` | Порядок источников курса |
| `FALLBACK_USD_RATE` | `80.0000` | Курс, если ни одного курса в базе ещё нет |
| `RATE_MIN` / `RATE_MAX` / `RATE_MAX_JUMP_PCT` | `20` / `500` / `20` | Проверка правдоподобности курса |
| `SECURE_SSL_REDIRECT` · `SECURE_HSTS_SECONDS` | `true` · `31536000` | HTTPS-редирект и HSTS |
| `SHOW_SAMPLE_REVIEWS` | `false` | **В продакшене только `false`** (образцы отзывов — для демо) |
| `SITE_MODE` | `live` | Не меняйте: `demo` отключает приём заявок |
| `DJANGO_DEBUG` | `false` | **Никогда не включайте на сервере** |

`DJANGO_SETTINGS_MODULE` в `.env` **не работает** (файл читается уже внутри настроек). Его задают systemd-юниты,
а для ручных команд — `export` (раздел 4).

## 4. Первичная настройка базы

`manage.py` по умолчанию использует настройки разработки, поэтому в каждой сессии на сервере сначала:

```bash
sudo -iu ivax
cd /srv/ivax/app
export DJANGO_SETTINGS_MODULE=config.settings.prod
.venv/bin/python manage.py check --deploy          # должно быть без ошибок
.venv/bin/python manage.py migrate
.venv/bin/python manage.py collectstatic --noinput
.venv/bin/python manage.py seed_catalog            # ТОЛЬКО при первой установке
.venv/bin/python manage.py update_rate
.venv/bin/python manage.py createsuperuser
```

- `seed_catalog` загружает 15 моделей из прайса (`apps/catalog/seed/catalog.json`), справочники опций и цветов,
  «Настройки сайта» и фото. **Повторный запуск перезапишет** изменения владельца в этих моделях (тексты, цены,
  публикацию, варианты) — после первой установки каталог ведётся только в админке.
- `createsuperuser` — учётная запись владельца (пароль не короче 12 символов). Сотрудникам — отдельные
  пользователи с ограниченными правами ([admin-guide.md](admin-guide.md#10-учётная-запись-менеджера-с-ограниченными-правами)).

## 5. Службы systemd

```bash
sudo cp /srv/ivax/app/deploy/ivax*.service /srv/ivax/app/deploy/ivax*.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now ivax.service ivax-notify.service ivax-rate.timer ivax-purge.timer
systemctl list-timers 'ivax*'
```

| Юнит | Что делает |
|------|------------|
| `ivax.service` | gunicorn `config.wsgi:application` на `127.0.0.1:8000`, 3 воркера; пишет только в `data/` и `media/` |
| `ivax-notify.service` | `send_notifications --loop --interval 5` — **единственный автоматический отправитель** уведомлений (Telegram, e-mail) из очереди Outbox. Если он остановлен, заявки сохраняются, но уведомления копятся |
| `ivax-rate.service` + `ivax-rate.timer` | `update_rate --soft` каждые 3 часа (в 00:05, 03:05, …) |
| `ivax-purge.service` + `ivax-purge.timer` | `purge_leads` ежедневно в 04:15: обезличивание заявок старше `LEAD_RETENTION_DAYS`, удаление отклонённых отзывов старше 90 дней |

Все юниты работают от пользователя `ivax`, с `ProtectSystem=strict`, `NoNewPrivileges` и `UMask=0027`.

## 6. Caddy (HTTPS)

```bash
sudo cp /srv/ivax/app/deploy/Caddyfile.example /etc/caddy/Caddyfile
sudo nano /etc/caddy/Caddyfile
sudo caddy validate --config /etc/caddy/Caddyfile
sudo systemctl restart caddy
```

В файле замените:
- `ivax-moto.ru, www.ivax-moto.ru` — на ваш домен;
- **оба** вхождения `/ВАШ-ПУТЬ-АДМИНКИ/*` — на `/<ADMIN_PATH>/*` из `.env`. Иначе загрузка фото и импорт Excel
  в админке упрутся в лимит 64 КБ для публичных адресов.

Caddy сам получает и продлевает TLS-сертификат, передаёт `X-Real-IP` и `X-Forwarded-Proto`, ограничивает тело
запроса (админка — 12 МБ, остальное — 64 КБ) и отдаёт `/media/` напрямую с диска со строгим CSP.
Статические файлы (`/static/`) отдаёт WhiteNoise внутри Django.

Проверка: откройте `https://<домен>/`, `https://<домен>/<ADMIN_PATH>/`, отправьте тестовую заявку и убедитесь,
что уведомление пришло (раздел 10).

## 7. Резервные копии

`deploy/backup.sh` делает копию БД через `sqlite3 .backup` (корректно для WAL) и архив фото, хранит 30 дней.

```bash
sudo crontab -u ivax -e
# добавить строку:
30 3 * * * /bin/sh /srv/ivax/app/deploy/backup.sh
```

- Копии содержат персональные данные: храните их только у себя и на втором хранилище **в РФ**, не в личных облаках.
  Регулярно копируйте `/srv/ivax/backups` за пределы сервера.
- **Восстановление:** остановить сайт, отправитель, оба таймера и активные oneshot-службы; сохранить аварийные
  данные и восстановить согласованный комплект БД, media и кода. Точные команды — в разделе 12 `DEPLOYMENT_VPS.md`.
- Раз в несколько месяцев проверяйте восстановление на тестовой машине.

## 8. Telegram-бот для менеджеров

1. В Telegram откройте **@BotFather** → `/newbot` → придумайте имя и логин бота → получите **токен**.
2. Создайте группу менеджеров, добавьте в неё бота и напишите в группе `/start@логин_бота`.
3. На сервере узнайте id чата (подставьте токен):
   ```bash
   curl -s "https://api.telegram.org/bot<ТОКЕН>/getUpdates"
   ```
   В ответе найдите `"chat":{"id":-100…` — это `TELEGRAM_CHAT_ID` (с минусом).
4. Впишите `TELEGRAM_BOT_TOKEN` и `TELEGRAM_CHAT_ID` в `.env` и перезапустите **обе** службы (сайт решает, ставить ли
   Telegram в очередь, отправитель — отправляет): `sudo systemctl restart ivax ivax-notify`.
5. Оставьте `TELEGRAM_INCLUDE_PD=false`: в Telegram уйдут модель, комплектация, цена и ссылка на заявку в админке,
   а имя и телефон — только в письме и в админке.

Токен — секрет. Если он утёк, в @BotFather выполните `/revoke`, впишите новый токен и перезапустите службы.

## 9. Почта (SMTP)

1. Заведите ящик на домене у российского провайдера (например, Яндекс 360 для бизнеса или VK WorkMail), скажем
   `noreply@ivax-moto.ru`, и создайте для него **пароль приложения**.
2. Добавьте в DNS домена записи SPF и DKIM по инструкции провайдера — иначе письма попадут в спам.
3. Заполните `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_USE_SSL`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`,
   `DEFAULT_FROM_EMAIL` (тот же ящик) и `LEAD_NOTIFY_EMAILS`.
4. `sudo systemctl restart ivax ivax-notify` и отправьте тестовую заявку.

В письме есть имя и телефон клиента. После успешной отправки текст письма в очереди удаляется.

## 10. Мониторинг

- **Админка → «Заявки» → «Уведомления (очередь)»:** записи «Не доставлено» или долго «Ожидает» — проверьте токен,
  SMTP и службу `ivax-notify`. Ошибка видна в колонке «Последняя ошибка».
- **Админка → «Настройки сайта» → «Курс сейчас»:** надпись «УСТАРЕЛ» — курс не обновлялся больше 3 дней.
  «Курсы валют» показывает отклонённые курсы с причиной.
- **Логи и таймеры:**
  ```bash
  journalctl -u ivax -u ivax-notify --since "1 hour ago"
  journalctl -u ivax-rate -u ivax-purge -n 50
  systemctl status ivax ivax-notify
  systemctl list-timers 'ivax*'
  df -h /srv
  ```
- Заблокированный вход в админку снимается в разделе «Axes» или командой
  `.venv/bin/python manage.py axes_reset_username <логин>`.

## 11. Обновление сайта

Обновлять можно только из `main` и только после зелёного CI. Полная последовательность с остановкой всех
писателей БД, резервной копией и проверкой плана миграций — в разделе 11
[DEPLOYMENT_VPS.md](../DEPLOYMENT_VPS.md#11-безопасное-обновление).

- Если в коммите менялись файлы `deploy/*.service` / `*.timer` — скопируйте их заново в `/etc/systemd/system/` и
  выполните `sudo systemctl daemon-reload`. Если менялся `Caddyfile.example` — перенесите изменения в
  `/etc/caddy/Caddyfile` вручную (с вашим доменом и путём админки) и `sudo systemctl reload caddy`.
- Новые переменные окружения появляются в `.env.example` — сверяйте его со своим `.env`.
- **Откат:** восстановить согласованный комплект кода, БД и media по разделу 12 `DEPLOYMENT_VPS.md`,
  предварительно сохранив аварийные данные. Оба таймера также должны быть остановлены.

## 12. Юридические шаги перед запуском (делает владелец)

- **Уведомление Роскомнадзора** об обработке персональных данных (ст. 22 152-ФЗ) — до начала сбора заявок,
  через портал pd.rkn.gov.ru. Укажите цели (обработка заявок), категории данных (имя, телефон), место хранения
  базы (VPS в РФ, провайдер), срок хранения. Если когда-нибудь будет включён `TELEGRAM_INCLUDE_PD=true`,
  нужно ещё уведомление о трансграничной передаче (ст. 12 152-ФЗ).
- Заменить заглушки `[…]` в «Настройках сайта» (продавец, ИНН, ОГРН, адрес) и согласовать с юристом тексты
  политики, согласий, соглашения и политики cookie.
- Назначить ответственного за обработку ПДн.
- Снять `noindex` (`SITE_NOINDEX=false`, `sudo systemctl restart ivax`) — **только по решению владельца**, после
  этого добавить сайт в Яндекс Вебмастер и Google Search Console и отправить `sitemap.xml`.
