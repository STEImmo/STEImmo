#!/usr/bin/env bash
# Exercise production settings and persistence with disposable local resources.
set -Eeuo pipefail
image=${1:?Aufruf: smoke.sh LOKALES_IMAGE}
project="steimmo-smoke-$$"
directory=$(mktemp -d /tmp/steimmo-smoke.XXXXXXXX)
repository=$(cd -- "$(dirname -- "$0")/.." && pwd)
export STEIMMO_IMAGE="$image" STEIMMO_ENV_FILE="$directory/.env"
compose_file="$repository/docker/compose.prod.yaml"
if command -v cygpath > /dev/null; then
    STEIMMO_ENV_FILE=$(cygpath -m "$STEIMMO_ENV_FILE")
    compose_file=$(cygpath -m "$compose_file")
    export MSYS_NO_PATHCONV=1
fi
export POSTGRES_VOLUME_NAME="$project-postgres" MEDIA_VOLUME_NAME="$project-media"
export STEIMMO_NETWORK_NAME="$project-network"
export POSTGRES_DB=steimmo POSTGRES_USER=steimmo POSTGRES_PASSWORD=ci-only-example-database-password
compose() {
    docker compose --project-name "$project" --env-file "$STEIMMO_ENV_FILE" \
        --file "$compose_file" "$@"
}
cleanup() {
    local status=$?
    trap - EXIT
    if (( status != 0 )); then compose logs --tail 60 web postgres >&2 || true; fi
    compose down > /dev/null 2>&1 || true
    docker volume rm "$POSTGRES_VOLUME_NAME" "$MEDIA_VOLUME_NAME" > /dev/null 2>&1 || true
    docker network rm "$STEIMMO_NETWORK_NAME" > /dev/null 2>&1 || true
    [[ $directory == /tmp/steimmo-smoke.* ]] && rm -rf -- "$directory"
    exit "$status"
}
trap cleanup EXIT
cat > "$STEIMMO_ENV_FILE" <<'ENV'
DJANGO_SECRET_KEY=ci-only-example-with-more-than-fifty-characters-never-use-in-production
DJANGO_ALLOWED_HOSTS=steimmo.example.test
DJANGO_CSRF_TRUSTED_ORIGINS=https://steimmo.example.test
DJANGO_LOGIN_THROTTLE_TRUSTED_PROXY_IPS=127.0.0.1
DJANGO_EMAIL_HOST=smtp.example.test
DJANGO_DEFAULT_FROM_EMAIL=noreply@example.test
POSTGRES_DB=steimmo
POSTGRES_USER=steimmo
POSTGRES_PASSWORD=ci-only-example-database-password
ENV
chmod 600 "$STEIMMO_ENV_FILE"
docker volume create "$POSTGRES_VOLUME_NAME" > /dev/null
docker volume create "$MEDIA_VOLUME_NAME" > /dev/null
docker network create "$STEIMMO_NETWORK_NAME" > /dev/null
compose config --quiet
[[ $(docker run --rm --entrypoint id "$image" -u) == 10001 ]]
docker run --rm --entrypoint python "$image" -c \
    'import importlib.util; assert importlib.util.find_spec("ruff") is None'
compose up --detach --wait --wait-timeout 120 postgres
if compose run --rm --no-deps -T web python manage.py deployment_preflight; then
    echo 'Auf einer frischen Datenbank wurden keine Migrationen erkannt.' >&2
    exit 1
else
    [[ $? == 3 ]]
fi
compose run --rm --no-deps -T web python manage.py migrate --noinput
compose run --rm --no-deps -T web python manage.py deployment_preflight
compose run --rm --no-deps -T web sh -ec \
    'python manage.py collectstatic --noinput; test -s /app/staticfiles/css/app.css; test -s /app/staticfiles/admin/css/base.css'
compose run --rm --no-deps -T web python -c \
    'from pathlib import Path; Path("/app/media/smoke.txt").write_text("persistent")'
compose exec -T postgres sh -ec \
    'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" --format=custom' > "$directory/database.dump"
compose exec -T postgres sh -ec 'createdb -U "$POSTGRES_USER" steimmo_smoke_restore'
compose exec -T postgres sh -ec \
    'pg_restore -U "$POSTGRES_USER" -d steimmo_smoke_restore --exit-on-error' < "$directory/database.dump"
[[ $(compose exec -T postgres sh -ec \
    'psql -U "$POSTGRES_USER" -d steimmo_smoke_restore -Atc "SELECT COUNT(*) > 0 FROM django_migrations"') == t ]]
compose run --rm --no-deps -T web tar -C /app/media -czf - . > "$directory/media.tar.gz"
compose run --rm --no-deps -T web sh -ec \
    'mkdir /tmp/media-restore; tar -xzf - -C /tmp/media-restore; test "$(cat /tmp/media-restore/smoke.txt)" = persistent' \
    < "$directory/media.tar.gz"
compose up --detach --no-build --wait --wait-timeout 120 web
curl --fail --silent --show-error -H 'Host: steimmo.example.test' -H 'X-Forwarded-Proto: https' \
    http://127.0.0.1:8010/health/ | grep -q '"status": "ok"'
[[ $(curl --silent --output /dev/null --write-out '%{http_code}' \
    -H 'Host: steimmo.example.test' http://127.0.0.1:8010/) == 301 ]]
compose up --detach --no-build --force-recreate --wait --wait-timeout 120 web
compose exec -T web python -c \
    'from pathlib import Path; assert Path("/app/media/smoke.txt").read_text() == "persistent"'
printf 'Produktions-Smoke-Test erfolgreich.\n'
