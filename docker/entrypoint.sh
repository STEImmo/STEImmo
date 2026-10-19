#!/bin/sh
set -eu

if [ "${DJANGO_BOOTSTRAP_ON_START:-0}" = "1" ]; then
    python manage.py migrate --noinput
    python manage.py collectstatic --noinput
fi

if [ "${DJANGO_CREATE_DEVELOPMENT_EMPLOYEE:-0}" = "1" ]; then
    : "${DJANGO_DEVELOPMENT_EMPLOYEE_EMAIL:?DJANGO_DEVELOPMENT_EMPLOYEE_EMAIL fehlt}"
    : "${DJANGO_DEVELOPMENT_EMPLOYEE_PASSWORD:?DJANGO_DEVELOPMENT_EMPLOYEE_PASSWORD fehlt}"
    python manage.py create_development_employee \
        --email "$DJANGO_DEVELOPMENT_EMPLOYEE_EMAIL" \
        --password "$DJANGO_DEVELOPMENT_EMPLOYEE_PASSWORD"
fi

exec "$@"
