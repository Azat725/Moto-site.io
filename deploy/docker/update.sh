#!/bin/sh
# Вызывать после git pull --ff-only. Код сначала собирается; при ошибке сборки сайт продолжает работать.
set -eu
cd "$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)"
IVAX_ENV_FILE=${1:-.env}
export IVAX_ENV_FILE

compose() {
    docker compose --env-file "$IVAX_ENV_FILE" "$@"
}

compose config --quiet
compose build --pull
# Все процессы записи остановлены до init (копия → проверки → миграции → статика).
compose stop caddy notify maintenance web
compose up -d --force-recreate --wait --wait-timeout 240
compose ps
