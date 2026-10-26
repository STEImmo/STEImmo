#!/usr/bin/env bash
# Verify migration authoring against real Linux checkout ownership.
set -Eeuo pipefail
image=${1:?Aufruf: smoke-development.sh DEVELOPMENT_IMAGE [UID] [GID]}
development_uid=${2:-1000}
development_gid=${3:-1000}
[[ $development_uid =~ ^[1-9][0-9]*$ && $development_gid =~ ^[1-9][0-9]*$ ]]
export MSYS_NO_PATHCONV=1
volume="steimmo-development-smoke-$$"
cleanup() {
    local status=$?
    trap - EXIT
    docker volume rm "$volume" > /dev/null 2>&1 || true
    exit "$status"
}
trap cleanup EXIT
docker volume create "$volume" > /dev/null
# A Docker volume uses Linux permissions even when the host is Docker Desktop.
# Populate the source from the image and model a host checkout owned by UID/GID.
docker run --rm --user 0:0 --entrypoint sh --volume "$volume:/app" "$image" -ec '
    chown "$1:$2" /app
    chmod 755 /app
    find /app -mindepth 1 -maxdepth 1 ! -name media ! -name staticfiles \
        -exec chown -R "$1:$2" {} +
' sh "$development_uid" "$development_gid"
# Keep media/static ownership from the development image; do not repair it here.
# shellcheck disable=SC2016
docker run --rm --entrypoint sh --volume "$volume:/app" \
    --env DJANGO_DEBUG=1 --env POSTGRES_HOST=127.0.0.1 --env POSTGRES_PORT=1 \
    "$image" -ec '
    python manage.py makemigrations core --empty --name permission_probe
    test -s core/migrations/*_permission_probe.py
    test "$(id -u)" = "$1"
    test "$(id -g)" = "$2"
    test "$(stat -c %u core/migrations/*_permission_probe.py)" = "$1"
    touch /app/media/.permission-probe /app/staticfiles/.permission-probe
' sh "$development_uid" "$development_gid"
printf 'Development-Smoke-Test: Migration und Laufzeitdateien als %s:%s geschrieben.\n' \
    "$development_uid" "$development_gid"
