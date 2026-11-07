# Moto-site.io — сайт IV&AX MOTO (электромотоциклы)

Сайт продажи электромотоциклов в Нижнекамске: каталог из 15 моделей по прайсу поставщика, страница модели с
конфигуратором (мощность и батарея, опции, цвет), заявка менеджеру, отзывы с модерацией, доставка и оплата,
юридические документы РФ, cookie-согласие, SEO-разметка. Владелец управляет всем в админке Django.

- **Цена** = (цена варианта $ + опции $) × курс USD ЦБ РФ + наценка 100 000 ₽, с округлением вверх до 1 000 ₽.
  Доставка не входит. Курс обновляется автоматически каждые 3 часа.
- **Заказ** — только через менеджера: онлайн-оплаты и регистрации нет. Заявка сохраняется в базе, менеджеру
  приходят уведомления в Telegram (без персональных данных) и на почту.
- **Стек:** Python 3.13+, Django 6.1, SQLite, django-axes, WhiteNoise, gunicorn + Caddy; ванильные JS/CSS.
- **Демо для согласования:** https://azat725.github.io/Moto-site.io/ (статический экспорт; формы не отправляются,
  отзывы — образцы с пометкой, закрыто от поисковиков).

> **Для ИИ-агентов (Codex, Kimi, Claude и др.):** сначала прочитайте [AGENTS.md](AGENTS.md) — контекст, правила,
> работа в `dev`/`feature/*` и влитие в `main` только после тестов.

## Быстрый старт (локально)
```bash
python -m venv .venv
# Windows: .venv\Scripts\activate      Linux/macOS: source .venv/bin/activate
pip install -r requirements-dev.txt
python -c "from pathlib import Path; Path('data').mkdir(exist_ok=True)"
python manage.py migrate
python manage.py seed_catalog        # 15 моделей, опции, цвета, фото из apps/catalog/seed/
python manage.py update_rate         # курс USD с сайта ЦБ РФ
python manage.py createsuperuser
python manage.py runserver           # http://127.0.0.1:8000
```
`manage.py` по умолчанию использует `config.settings.dev` (DEBUG, письма выводятся в консоль, образцы отзывов).
Админка: http://127.0.0.1:8000/manage-ivax/ (в продакшене путь задаётся случайным `ADMIN_PATH`).
Файл `.env` локально не обязателен; переменные — в [.env.example](.env.example).

## Тесты
```bash
python -m pytest                                          # unit + integration
python -m pytest --cov=apps --cov-fail-under=80           # как в CI
RUN_E2E=1 python -m pytest -m e2e tests/e2e               # E2E Playwright в установленном Google Chrome
# PowerShell: $env:RUN_E2E="1"; python -m pytest -m e2e tests/e2e
```
CI (`.github/workflows/ci.yml`) на каждый push в `dev`, `main`, `feature/**` и PR: `manage.py check`,
`makemigrations --check`, pytest с покрытием ≥ 80 %, `check --deploy` с продакшен-настройками.

## Статическое демо (GitHub Pages)
```bash
DJANGO_SETTINGS_MODULE=config.settings.pages python manage.py export_static   # → _site/
python scripts/preview_pages.py                                                # → http://localhost:5174/Moto-site.io/
```
PowerShell: `$env:DJANGO_SETTINGS_MODULE="config.settings.pages"; python manage.py export_static`.
Флаг `--no-rate` — собрать без обращения к ЦБ. Workflow `.github/workflows/pages.yml` собирает и публикует демо
при каждом push в `main`, ежедневно в 16:00 МСК и вручную. Для работы нужно один раз включить
**Settings → Pages → Source = GitHub Actions** (делает владелец репозитория).

## Структура
```
config/            настройки (base, dev, test, pages, prod), urls.py, wsgi.py
apps/catalog/      модели, варианты, опции, цвета, фото, цены, импорт/экспорт Excel, исходный прайс (seed/)
apps/rates/        курс ЦБ РФ
apps/leads/        заявки, очередь уведомлений, Telegram и e-mail
apps/reviews/      отзывы с модерацией
apps/pages/        страницы, SEO, экспорт демо
templates/ static/ шаблоны, CSS, JS, графика
tests/             unit, integration, e2e
deploy/            systemd, Caddy, резервное копирование
scripts/           предпросмотр демо, приглашение партнёра, служебные инструменты
docs/              документация
```

## Документация
- [Docker Compose: установка и обновление одной командой](docs/deploy-docker.md)
- [DEPLOYMENT_VPS.md](DEPLOYMENT_VPS.md) — полная инструкция SSH → установка → приёмка → обновление и восстановление
- [docs/architecture.md](docs/architecture.md) — устройство кода, модель данных, цены, курс, безопасность
- [docs/deploy-vps.md](docs/deploy-vps.md) — установка и обновление на сервере в РФ
- [docs/admin-guide.md](docs/admin-guide.md) — инструкция для владельца по админке
- [docs/import-format.md](docs/import-format.md) — формат таблицы импорта каталога
- [CONTRIBUTING.md](CONTRIBUTING.md) — ветки и порядок работы, [AGENTS.md](AGENTS.md) — полные правила

## Ветки и партнёр-разработчик
- `main` — стабильная (публикует демо, с неё обновляется сервер), `dev` — рабочая, `feature/*` — задачи.
  В `main` — только после тестов. Подробнее: [CONTRIBUTING.md](CONTRIBUTING.md).
- **Добавить партнёра** (владелец репозитория): `winget install --id GitHub.cli`, один раз `gh auth login`, затем
  `./scripts/invite-partner.ps1 -Login <github-логин-партнёра>` и отправить партнёру ссылку из вывода
  (`https://github.com/<владелец>/Moto-site.io/invitations`). Либо *Settings → Collaborators → Add people*.

## Перед запуском рабочего сайта
Для Docker используйте [docs/deploy-docker.md](docs/deploy-docker.md). После первичной настройки обновление:

```bash
cd /srv/ivax/app && git pull --ff-only && sh deploy/docker/update.sh
```

1. Сервер в РФ, домен, `.env`, службы — по [docs/deploy-vps.md](docs/deploy-vps.md).
2. В админке «Настройки сайта» — реальные телефон, e-mail, адрес, продавец, ИНН, ОГРН (сейчас заглушки `[…]`).
3. Юридические документы (`templates/pages/legal/`) — согласовать с юристом. **Шаблоны не заменяют консультацию юриста.**
4. Уведомить Роскомнадзор об обработке персональных данных (ст. 22 152-ФЗ).
5. Запросить у поставщика фото без водяного знака и загрузить их в админке.
6. Снять `noindex` (`SITE_NOINDEX=false`) — только по решению владельца; затем Яндекс Вебмастер, Google Search Console.

## Материалы
- Прайс-листы поставщика (PDF) хранятся локально в `_private/` и в репозиторий не попадают. Фото моделей вырезаны
  из прайса скриптом `scripts/tools/extract_bike_photos.py` (нужен `pymupdf`) и содержат водяной знак поставщика.
- Бренд производителя и контакты поставщика на сайте не показываются; формулировка «под заказ» не используется.
- `scripts/tools/make_brand_assets.py` — перегенерация `favicon.svg` и `og-image.png` (нужен Chrome или Edge).

Лицензия: проприетарная, см. [LICENSE](LICENSE).
