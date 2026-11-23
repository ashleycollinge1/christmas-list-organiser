#!/bin/sh
set -eu

case "${1:-web}" in
  web)
    alembic upgrade head
    exec uvicorn app.main:app \
      --host 0.0.0.0 --port 8000 \
      --proxy-headers --forwarded-allow-ips="${FORWARDED_ALLOW_IPS:-*}" \
      --no-server-header --timeout-keep-alive 75
    ;;
  migrate)
    exec alembic upgrade head
    ;;
  *)
    exec "$@"
    ;;
esac
