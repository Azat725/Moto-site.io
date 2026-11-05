# Как работать над проектом

> ИИ-агентам и разработчикам: подробные правила, чек-лист тестирования и юридические ограничения — в [AGENTS.md](AGENTS.md). Влить `dev` в `main` можно только после успешного `npm run check` и ручной проверки на 375/768/1280 px: `main` публикуется на GitHub Pages сразу.

## Ветки
| Ветка | Назначение |
|-------|------------|
| `main` | Стабильная версия сайта. То, что видят посетители. Прямых коммитов нет — только через Pull Request из `dev`. |
| `dev`  | Рабочая ветка. Сюда сливаются все доработки. |
| `feature/<название>` | Короткоживущие ветки под задачу, создаются от `dev`. |

## Рабочий процесс
```bash
git clone https://github.com/<владелец>/Moto-site.io.git
cd Moto-site.io
git checkout dev
git checkout -b feature/my-change
# ...правки в src/, css/, js/, assets/
node scripts/build.mjs        # пересобрать страницы
git add -A && git commit -m "feat: что сделано"
git push -u origin feature/my-change
# открыть Pull Request в ветку dev
```

## Правила
- Страницы редактируем в `src/` (HTML-шаблоны), **корневые `*.html` и `bikes/*.html` — результат сборки**, руками не правим.
- Каталог мотоциклов — `src/data/motorcycles.json`; контакты, реквизиты, домен — `site.config.json`.
- Анимируем только `transform` и `opacity`; обязательно учитываем `prefers-reduced-motion`.
- Не добавляем чужие фото/тексты без прав. Для заглушек — SVG из `assets/`.
- Коммиты: `feat:`, `fix:`, `content:`, `docs:`, `chore:`.
- Секреты (ключи, токены) в репозиторий не кладём.
