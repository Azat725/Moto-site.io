# syntax=docker/dockerfile:1
FROM python:3.13-slim-trixie@sha256:09a17cad02668ae61ece136b4fd36ac3849e14f670ebedb637ea3e15580525bc

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 \
    DJANGO_SETTINGS_MODULE=config.settings.prod \
    DATA_DIR=/srv/ivax/data MEDIA_ROOT=/srv/ivax/media BACKUP_DIR=/srv/ivax/backups

RUN apt-get update && apt-get install -y --no-install-recommends tzdata \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --gid 10001 ivax && useradd --uid 10001 --gid ivax --no-create-home ivax
WORKDIR /srv/ivax/app
COPY requirements.txt ./
RUN python -m pip install -r requirements.txt && python -m pip check
COPY --chown=10001:10001 manage.py ./
COPY --chown=10001:10001 config/ config/
COPY --chown=10001:10001 apps/ apps/
COPY --chown=10001:10001 templates/ templates/
COPY --chown=10001:10001 static/ static/
COPY --chown=10001:10001 deploy/docker/ deploy/docker/
RUN mkdir -p /srv/ivax/data /srv/ivax/media /srv/ivax/backups /srv/ivax/app/staticfiles \
    && chown -R 10001:10001 /srv/ivax/data /srv/ivax/media /srv/ivax/backups /srv/ivax/app/staticfiles \
    && chmod 700 /srv/ivax/data /srv/ivax/backups && chmod 750 /srv/ivax/media
USER 10001:10001
ENTRYPOINT ["sh", "/srv/ivax/app/deploy/docker/entrypoint.sh"]
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3", "--timeout", "30", "--max-requests", "1000", "--max-requests-jitter", "100"]
