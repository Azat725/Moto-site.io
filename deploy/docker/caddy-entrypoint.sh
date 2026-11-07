#!/bin/sh
set -eu
export CADDY_ADMIN_PATH="$(printf '%s' "$ADMIN_PATH" | tr -d '/')"
exec caddy run --config /etc/caddy/Caddyfile --adapter caddyfile
