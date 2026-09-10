#!/bin/sh
# usage: entrypoint.sh api|worker|scheduler|migrate|seed
set -e
case "$1" in
  api)       alembic upgrade head && python -m app.seed && exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers --forwarded-allow-ips='*' ;;
  worker)    exec arq app.tasks.worker.WorkerSettings ;;
  scheduler) exec python -m app.scheduler.main ;;
  migrate)   exec alembic upgrade head ;;
  seed)      exec python -m app.seed ;;
  *)         exec "$@" ;;
esac
