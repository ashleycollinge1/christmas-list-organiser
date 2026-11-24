#!/bin/sh
set -eu

case "${1:-web}" in
  web)
    if ! out=$(alembic upgrade head 2>&1); then
      echo "$out"
      case "$out" in
        *"Can't locate revision"*)
          echo "ERROR: this database was upgraded by a newer version of Christmas List Organiser," >&2
          echo "so this older version can't use it. Either use the newer version's compose file," >&2
          echo "or roll back properly by restoring the backup taken before the upgrade:" >&2
          echo "  docker compose exec backup restore-backup christmas-<date>_before-<newer version>.dump" >&2
          echo "(see the release notes for the exact steps)." >&2
          ;;
      esac
      exit 1
    fi
    echo "$out"
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
