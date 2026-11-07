#!/bin/sh
# Ежедневная резервная копия БД (корректно для режима WAL) и фото. Запуск из cron: 30 3 * * *
set -eu
STAMP=$(date +%Y%m%d)
mkdir -p /srv/ivax/backups
sqlite3 /srv/ivax/data/db.sqlite3 ".backup '/srv/ivax/backups/db-$STAMP.sqlite3'"
tar -czf "/srv/ivax/backups/media-$STAMP.tar.gz" -C /srv/ivax media
find /srv/ivax/backups -type f -mtime +30 -delete
