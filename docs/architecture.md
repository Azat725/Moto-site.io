# Архитектура сайта IV&AX MOTO

**Обновлено:** 2026-11-07 · **Стек:** Python 3.13+, Django 6.1, SQLite (WAL), gunicorn + Caddy, ванильные JS/CSS
**Точки входа:** `manage.py` (по умолчанию `config.settings.dev`), `config/wsgi.py` (по умолчанию `config.settings.prod`), `config/urls.py`

Сайт — витрина электромотоциклов с конфигуратором и приёмом заявок. Онлайн-оплаты и регистрации покупателей нет:
каждый заказ оформляет менеджер. Владелец управляет каталогом, ценами, заявками и отзывами в админке Django.

## 1. Общая схема

```
Браузер ──HTTPS──> Caddy (TLS, лимит тела запроса, /media/ напрямую с диска)
                     │ X-Real-IP, X-Forwarded-Proto
                     v
                 gunicorn (ivax.service, 3 воркера) ── Django (config.settings.prod)
                     │                                   │
                     │       SQLite /srv/ivax/data/db.sqlite3 (WAL)  <── ivax-notify.service
                     │                                   ^               (send_notifications --loop:
                     │                                   │                Telegram, e-mail)
                     │                                   ├── ivax-rate.timer  → update_rate --soft (каждые 3 ч)
                     │                                   └── ivax-purge.timer → purge_leads (ежедневно 04:15)
                     v
                 WhiteNoise отдаёт /static/ (collectstatic → staticfiles/)

GitHub Actions: ci.yml (тесты) и pages.yml (export_static → статическое демо на GitHub Pages)
```

## 2. Приложения и зоны ответственности

| Приложение | За что отвечает | Ключевые файлы |
|------------|-----------------|----------------|
| `apps/catalog` | Модели, варианты (мощность/АКБ), опции, цвета, фото, «Настройки сайта» (наценка, округление, курс, контакты, реквизиты); расчёт цен; импорт/экспорт Excel/CSV; загрузка исходного прайса | `models.py`, `pricing.py`, `services.py`, `catalog_io.py`, `spreadsheet.py`, `admin.py`, `admin_import.py`, `images.py`, `seed_loader.py`, `seed/catalog.json`, `seed/photos/*.webp`, команда `seed_catalog` |
| `apps/rates` | Курс USD/RUB ЦБ РФ: получение, проверка, история, выбор текущего | `models.py` (`Rate`), `parsers.py`, `services.py`, `admin.py`, команда `update_rate` |
| `apps/leads` | Заявки: валидация, антиспам, лимиты, пересчёт цены, очередь уведомлений Outbox, доставка, обезличивание | `forms.py`, `views.py`, `services.py`, `ratelimit.py`, `delivery.py`, `notifiers.py`, `admin.py`, команды `send_notifications`, `purge_leads` |
| `apps/reviews` | Отзывы покупателей с модерацией и двумя согласиями | `models.py`, `forms.py`, `views.py`, `admin.py` |
| `apps/pages` | Публичные страницы, SEO (JSON-LD, sitemap, robots), контекст шаблонов, иконки/логотипы, защита публичных POST, экспорт статического демо | `views.py`, `urls.py`, `viewmodels.py`, `content.py`, `seo.py`, `sitemaps.py`, `context_processors.py`, `middleware.py`, `icons.py`, `templatetags/site_tags.py`, команда `export_static` |
| `config` | Настройки и маршруты | `settings/base.py`, `dev.py`, `test.py`, `pages.py`, `prod.py`, `env.py` (чтение `.env` без внешних зависимостей), `urls.py` |

### Модули настроек

| Модуль | Где используется | Особенности |
|--------|------------------|-------------|
| `config.settings.dev` | `manage.py` по умолчанию, локальная работа | `DEBUG=True`, письма в консоль, образцы отзывов включены |
| `config.settings.test` | `pytest.ini` | БД в памяти, быстрый хешер паролей, тестовые Telegram/e-mail |
| `config.settings.pages` | `export_static`, `pages.yml` | `SITE_MODE=demo`, `noindex`, префикс `/Moto-site.io/`, отдельная БД `data/pages-build.sqlite3` |
| `config.settings.prod` | `config/wsgi.py`, systemd-юниты | Требует `DJANGO_SECRET_KEY` (≥ 50 символов), свой `IP_HASH_SALT`, свой `ADMIN_PATH`; HTTPS, HSTS, secure-cookie, сжатые статические файлы с манифестом |

## 3. Модель данных

```
SiteSettings (одна запись pk=1): markup_rub, rounding_step, rate_mode, manual_rate, контакты, реквизиты, соцсети
Motorcycle ──< Variant          label, battery_ah, price_usd (пусто = «цена по запросу»), переопределения характеристик
     │     ──< MotorcycleOption ──> OptionDef (справочник: code, name)    status: optional (за доплату, price_usd) | included
     │     ──< Photo            image (WebP), alt, sort_order
     │     >──< Color           code, name, hex   (не выбраны цвета — на сайте показываются все)
Rate        currency, value, effective_date, source, accepted, note
Lead ──< Outbox                 channel (telegram|email), status (pending|sending|sent|dead), attempts, next_attempt_at
Review ──> Motorcycle           status (pending|approved|rejected), consent_at, publication_consent_at
```

- Пустые характеристики варианта берутся из модели (`Variant.spec()`).
- `Motorcycle.supplier_ref` и `origin_country` — служебные, на сайте не выводятся.
- `Lead.config` — снимок конфигурации на момент заявки: вариант, опции, цвет, курс и его дата, наценка, шаг,
  цена, которую видел клиент (`client_total`), и пометка `error`, если конфигурацию нужно уточнить.
- Право `leads.export_lead` («Выгрузка заявок с персональными данными») — отдельно от стандартных прав.

## 4. Цена: формула и округление

Цена поставщика хранится в долларах. Рублёвая цена считается при каждом показе страницы:

```
цена, ₽ = ceil_до_шага( (цена варианта $ + сумма выбранных опций $) × курс USD ЦБ РФ + наценка )
```

Точная реализация (`apps/catalog/pricing.py`, одинаково на сервере и в `static/js/configurator.js`):

1. Каждый компонент переводится в **копейки** отдельно: `round_half_up(цена_$ × курс × 100)`.
2. К компоненту варианта прибавляется наценка (`markup_rub × 100`, по умолчанию 100 000 ₽).
3. Опции со статусом «Входит в комплектацию» стоят 0.
4. Итог = сумма компонентов, округлённая **вверх** до шага (`rounding_step`, по умолчанию 1 000 ₽).
5. Доплата за опцию на карточке показывается округлённой вверх до рубля.

Пример: курс 81,1234; вариант 2 285 $ → 18 536 697 коп. + 10 000 000 коп. наценки; опция 120 $ → 973 481 коп.;
итог 29 510 178 коп. → **296 000 ₽**, доплата за опцию «+9 735 ₽».

Доставка в цену не входит (рассчитывается менеджером). Цена ориентировочная и не является публичной офертой.

**Почему браузер получает только рублёвые компоненты.** `Offer.as_json()` отдаёт конфигуратору
`{step, variants: [{id, label, kop}], options: [{code, kop, included}]}` — уже готовые копейки. Цены поставщика
в долларах и размер наценки в HTML/JS не попадают. Браузер лишь складывает компоненты и округляет до шага —
результат совпадает с серверным. При заявке сервер **пересчитывает** цену сам (`services.quote`), а цену из браузера
сохраняет только для сравнения (`price_changed` в ответе API, `client_total` в заявке).

## 5. Курс валют (`apps/rates`)

- Источники по порядку (`RATE_SOURCES`): `cbr_xml` — `https://www.cbr.ru/scripts/XML_daily.asp`,
  затем `cbr_json` — зеркало `https://www.cbr-xml-daily.ru/daily_json.js`. Таймаут 8 с, ответ не больше 512 КБ,
  XML разбирается через `defusedxml` с запретом DTD.
- Проверка нового курса: диапазон `RATE_MIN`–`RATE_MAX` (20–500 ₽); скачок больше `RATE_MAX_JUMP_PCT` (20 %)
  относительно последнего принятого отклоняется. Отклонённый курс сохраняется с `accepted=False` и причиной;
  если следующая попытка даёт почти тот же курс (±1 %), он принимается.
- Выбор курса для цен (`current_rate`): **ручной** (если в «Настройках сайта» выбран режим «Вручную» и указан курс)
  → **последний принятый** из ЦБ → **запасной** `FALLBACK_USD_RATE` (80 ₽, помечается как устаревший).
  Курс старше 3 дней помечается «УСТАРЕЛ» в «Настройках сайта».
- Обновление: таймер `ivax-rate.timer` каждые 3 часа (`update_rate --soft`), вручную — действие
  «Обновить курс с сайта ЦБ РФ сейчас» в админке «Курсы валют» или `python manage.py update_rate`.

## 6. Потоки запросов

### Каталог → модель → конфигуратор
1. `/` и `/catalog/` — `published_motorcycles()` (только `is_published=True`) → `build_offer()` для каждой модели
   → карточки с ценой «от», фильтры по типу, линейке и мощности (`static/js/catalog.js`).
2. `/moto/<slug>/` — характеристики, фото, варианты, опции, цвета, отзывы по модели. Данные конфигуратора
   выводятся тегом `{% cfg_json %}`; `static/js/configurator.js` пересчитывает цену при выборе.

### Заявка → Outbox → отправитель
```
форма (lead_form.html, forms.js) ──POST /api/leads/──> PublicUploadGuardMiddleware (≤ 64 КБ, без файлов)
  → CSRF → LeadForm (имя, телефон → +7…, согласие обязательно, honeypot website, подписанная метка времени)
  → лимит частоты по БД (5 заявок / 10 мин с IP или IPv6-сети /64)
  → create_lead(): пересчёт цены на сервере; ОДНА транзакция: Lead + записи Outbox (Telegram, e-mail)
  → ответ JSON 201 {id, total_rub, price_changed} или редирект на /thanks/
ivax-notify.service (send_notifications --loop, каждые 5 с):
  due_ids() → claim() (атомарный захват на 120 с, без двойной отправки) → send_telegram / send_email
  ошибка → повтор через 1 мин, 5 мин, 30 мин, 2 ч, 6 ч, 12 ч, 24 ч; после 8 попыток — «Не доставлено»
```
- Заявку с контактами не теряем: если модель снята с публикации или конфигурация устарела, заявка сохраняется
  с пометкой «Конфигурацию нужно уточнить». Подозрение на бота — статус «Спам», уведомления не создаются.
- Сайт не отправляет уведомления в момент заявки: автоматически это делает только `ivax-notify.service`.
  Кнопка «Повторить отправку сейчас» только перепланирует ожидающие/недоставленные записи; отправляет worker.
- Текст письма в Outbox после успешной отправки заменяется на «[отправлено, текст удалён]».

### Отзывы
`POST /reviews/submit/` → `ReviewForm` (имя, город, оценка 1–5, текст 20–1000 символов, два обязательных
согласия: на обработку ПДн и на публикацию имени и города) → лимит 3 отзыва в сутки с IP → статус «На модерации».
На сайте показываются только «Опубликован». При модерации хэш IP стирается.
Если одобренных отзывов нет и `SHOW_SAMPLE_REVIEWS=true` (dev и демо), показываются образцы, подписанные
«Пример отзыва» (`apps/pages/content.py`). В продакшене образцы выключены.

## 7. Режимы: live и demo

| | live (VPS) | demo (GitHub Pages) |
|---|---|---|
| Настройки | `config.settings.prod` | `config.settings.pages` |
| Формы | принимаются | `/api/leads/` и `/reviews/submit/` отвечают 403, CSRF-токен не выводится |
| Отзывы | только одобренные | образцы с пометкой «Пример отзыва» |
| Индексация | `SITE_NOINDEX` (по умолчанию закрыта) | всегда `noindex` |
| Плашка | нет | «Демо-версия для согласования…» |
| Данные | рабочая БД | `data/pages-build.sqlite3`: каждый раз `migrate` + `seed_catalog` + `update_rate --soft` |

`export_static` рендерит страницы через тестовый клиент Django в `_site/`: все маршруты из `STATIC_ROUTES`,
страницы опубликованных моделей, `sitemap.xml`, `robots.txt`, `404.html`, копирует `static/` и фото, создаёт
`.nojekyll`. Флаг `--no-rate` — без обращения к ЦБ (будет курс из базы или запасной). `pages.yml` собирает демо
при каждом push в `main`, ежедневно в 16:00 МСК (после обновления курса ЦБ) и вручную.

## 8. Маршруты

| Адрес | Что это |
|-------|---------|
| `/` · `/catalog/` · `/moto/<slug>/` | Главная, каталог, страница модели с конфигуратором |
| `/reviews/` · `/delivery/` · `/about/` · `/contacts/` | Отзывы, доставка и оплата, о компании, контакты |
| `/privacy/` · `/consent/` · `/consent-publication/` · `/terms/` · `/cookies/` | Юридические документы |
| `/thanks/` · `/preview/home-classic/` · `/preview/logo/` | Служебные (`noindex`) |
| `/api/leads/` · `/reviews/submit/` | Приём заявок и отзывов (только POST) |
| `/robots.txt` · `/sitemap.xml` | При `SITE_NOINDEX=true` robots запрещает всё |
| `/<ADMIN_PATH>` | Админка (путь из `.env`, в dev — `/manage-ivax/`) |
| `/bikes/*.html`, `/index.html`, `/catalog.html` и др. | Постоянные редиректы со старого статического сайта |

## 9. Безопасность и персональные данные

- **CSP** (встроенный `ContentSecurityPolicyMiddleware` Django 6.1): скрипты только свои и с nonce
  (`{{ csp_nonce }}`), картинки — свои и `data:`, `frame-ancestors 'none'`, `form-action 'self'`, внешних CDN,
  шрифтов и трекеров нет. Подключение счётчиков (Яндекс.Метрика и т. п.) потребует расширить `SECURE_CSP`
  в `config/settings/base.py`; загружаются они только после согласия на cookie (`static/js/cookie.js`).
- **Вход в админку:** `django-axes` — 5 неудачных попыток для пары «логин + IP» блокируют вход на 15 минут;
  пароль не короче 12 символов (scrypt); путь админки задаётся случайным `ADMIN_PATH`; сессия 12 часов.
- **Лимиты частоты** считаются по записям в БД (`apps/leads/ratelimit.py`), поэтому работают при нескольких
  воркерах gunicorn. IP берётся из `X-Real-IP` только если `TRUSTED_PROXY=true` и запрос пришёл с адреса
  из `TRUSTED_PROXY_IPS`. В БД хранится не IP, а HMAC-хэш с солью `IP_HASH_SALT`.
- **Защита загрузок** (`apps/pages/middleware.py`): вне админки POST/PUT/PATCH больше 64 КБ → 413,
  `multipart/form-data` → 415. Тот же лимит повторяет Caddy. Фото в админке: только JPEG/PNG/WebP до 10 МБ
  и 40 Мп, перекодируются в WebP (сторона ≤ 1800 px) без EXIF со случайным именем. Импорт Excel/CSV:
  до 5 МБ, 2000 строк, проверка распакованного размера `.xlsx` (≤ 50 МБ). При выгрузке в Excel/CSV значения,
  в Excel сохраняются с явным строковым типом без выполнения формул и без изменения исходного текста.
  В CSV заявок опасные префиксы `=`, `+`, `-`, `@`, табуляция и возврат каретки экранируются апострофом.
- **ПДн (152-ФЗ):** отдельный неотмеченный чекбокс согласия на каждой форме; сохраняются время согласия и
  его версия (`CONSENT_VERSION`). Собираются только имя, телефон, способ связи, комментарий и конфигурация.
  Telegram (серверы за рубежом) по умолчанию получает заявку **без имени и телефона** — только модель,
  комплектацию, цену и ссылку на заявку в админке (`TELEGRAM_INCLUDE_PD=false`). Контакты приходят письмом
  через российского SMTP-провайдера. Заявки старше `LEAD_RETENTION_DAYS` (1095 дней) обезличиваются
  автоматически (`purge_leads`), отклонённые отзывы удаляются через 90 дней. SQLite работает с
  `secure_delete=ON`. Токен бота не попадает в логи (`urllib3` на уровне WARNING, ошибки без URL).
- **Шаблоны** экранируют вывод по умолчанию; JSON-LD и данные конфигуратора выводятся через безопасные теги
  (`json_script_ld`, `cfg_json`).

## 10. Внешние зависимости

| Пакет | Назначение |
|-------|------------|
| Django 6.1.3 | Фреймворк, админка, CSP, sitemap |
| django-axes 9.0.0 | Защита входа от подбора пароля |
| whitenoise 6.12.0 | Отдача статических файлов |
| gunicorn 26.2.0 | WSGI-сервер в продакшене |
| openpyxl 3.1.5 | Импорт и экспорт Excel |
| defusedxml 0.7.1 | Безопасный разбор XML ЦБ РФ |
| pillow 13.0.0 | Проверка и перекодирование фото |
| requests 2.34.2 | Запросы к ЦБ РФ и Telegram |
| pytest, pytest-django, pytest-cov, responses, playwright | Только для разработки (`requirements-dev.txt`) |

## Связанные документы
- [deploy-vps.md](deploy-vps.md) — установка и обновление на сервере
- [admin-guide.md](admin-guide.md) — инструкция для владельца
- [import-format.md](import-format.md) — формат таблицы импорта каталога
- [../AGENTS.md](../AGENTS.md) — правила работы с репозиторием
