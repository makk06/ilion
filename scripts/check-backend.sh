#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
docker build --platform linux/arm64 --target test -t ilion-backend-check .
docker run --rm --network none -e DJANGO_DEBUG=true ilion-backend-check python manage.py test --noinput
docker run --rm --network none -e DJANGO_DEBUG=true ilion-backend-check python manage.py makemigrations --check --dry-run
docker run --rm --network none -e DJANGO_DEBUG=false -e DJANGO_SECRET_KEY=offline-smoke-only-never-use-in-production-1234567890-abcdefghij -e APP_BASE_URL=https://ilion.example.test -e DATA_WORKER_ENABLED=false ilion-backend-check python manage.py check --deploy --fail-level WARNING
