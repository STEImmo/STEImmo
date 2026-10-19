#!/usr/bin/env bash
# Exercise production settings and persistence with disposable local resources.
set -Eeuo pipefail
image=${1:?Aufruf: smoke.sh LOKALES_IMAGE}
mode=${2:-production}
[[ $mode == production || $mode == demo ]]
export STEIMMO_SETTINGS_MODULE="config.settings_$mode"
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
export STEIMMO_BIND_IP
STEIMMO_BIND_IP=$(docker network inspect bridge --format '{{(index .IPAM.Config 0).Gateway}}')
proxy_host=$STEIMMO_BIND_IP
# Docker Desktop publishes on its outer host rather than on the Linux VM's docker0.
if [[ $(docker info --format '{{.OperatingSystem}}') == *'Docker Desktop'* ]]; then
    STEIMMO_BIND_IP=127.0.0.1
    proxy_host=host.docker.internal
fi
public_volume="$project-public"
proxy_network="$project-proxy"
caddy=''
export POSTGRES_DB=steimmo POSTGRES_USER=steimmo POSTGRES_PASSWORD=ci-only-example-database-password
compose() {
    docker compose --project-name "$project" --env-file "$STEIMMO_ENV_FILE" \
        --file "$compose_file" "$@"
}
cleanup() {
    local status=$?
    trap - EXIT
    if (( status != 0 )); then compose logs --tail 60 web postgres >&2 || true; fi
    if [[ -n $caddy ]]; then
        if (( status != 0 )); then docker logs --tail 60 "$caddy" >&2 || true; fi
        docker rm --force --volumes "$caddy" > /dev/null 2>&1 || true
    fi
    compose down > /dev/null 2>&1 || true
    docker volume rm "$POSTGRES_VOLUME_NAME" "$MEDIA_VOLUME_NAME" "$public_volume" > /dev/null 2>&1 || true
    docker network rm "$STEIMMO_NETWORK_NAME" "$proxy_network" > /dev/null 2>&1 || true
    [[ $directory == /tmp/steimmo-smoke.* ]] && rm -rf -- "$directory"
    exit "$status"
}
trap cleanup EXIT
cat > "$STEIMMO_ENV_FILE" <<'ENV'
DJANGO_SECRET_KEY=ci-only-example-with-more-than-fifty-characters-never-use-in-production
DJANGO_ALLOWED_HOSTS=steimmo.example.test,localhost
DJANGO_CSRF_TRUSTED_ORIGINS=https://steimmo.example.test,https://localhost
DJANGO_LOGIN_THROTTLE_TRUSTED_PROXY_IPS=127.0.0.1
DJANGO_EMAIL_HOST=smtp.example.test
DJANGO_DEFAULT_FROM_EMAIL=noreply@example.test
POSTGRES_DB=steimmo
POSTGRES_USER=steimmo
POSTGRES_PASSWORD=ci-only-example-database-password
ENV
chmod 600 "$STEIMMO_ENV_FILE"
if [[ $mode == demo ]]; then
    sed -i 's/^DJANGO_EMAIL_HOST=.*/DJANGO_EMAIL_HOST=CHANGE_ME/; s/^DJANGO_DEFAULT_FROM_EMAIL=.*/DJANGO_DEFAULT_FROM_EMAIL=CHANGE_ME/' "$STEIMMO_ENV_FILE"
fi
docker volume create "$POSTGRES_VOLUME_NAME" > /dev/null
docker volume create "$MEDIA_VOLUME_NAME" > /dev/null
docker volume create "$public_volume" > /dev/null
docker network create "$STEIMMO_NETWORK_NAME" > /dev/null
docker network create "$proxy_network" > /dev/null
# Use the actual site snippet, with an isolated local TLS authority for the smoke test.
sed -e 's/steimmo-projekt-page.justus.software/localhost/' \
    -e "s/172.17.0.1:8010/$proxy_host:8010/" \
    -e '/^localhost {/a\    tls internal' "$repository/ops/caddy-steimmo.caddy" > "$directory/Caddyfile"
caddy=$(docker create --network "$proxy_network" \
    --volume "$public_volume:/srv/steimmo/public:ro" caddy:2.10.2)
caddy_file="$directory/Caddyfile"
if command -v cygpath > /dev/null; then caddy_file=$(cygpath -m "$caddy_file"); fi
docker cp "$caddy_file" "$caddy:/etc/caddy/Caddyfile"
docker start "$caddy" > /dev/null
proxy_source=$(bash "$repository/ops/proxy-source.sh" "$caddy" "$STEIMMO_BIND_IP" "$image" "$proxy_host")
sed -i "s/^DJANGO_LOGIN_THROTTLE_TRUSTED_PROXY_IPS=.*/DJANGO_LOGIN_THROTTLE_TRUSTED_PROXY_IPS=$proxy_source/" "$STEIMMO_ENV_FILE"
docker run --rm --user 0:0 --entrypoint sh --volume "$public_volume:/out" "$image" \
    -ec 'mkdir -p /out/releases/one; chown 10001:10001 /out/releases/one; ln -s releases/one /out/current'
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
if [[ $mode == demo ]]; then
    compose run --rm --no-deps -T web python manage.py setup_demo
    compose run --rm --no-deps -T web python manage.py setup_demo
fi
compose run --rm --no-deps -T web python manage.py deployment_preflight
docker run --rm --network "$STEIMMO_NETWORK_NAME" --env-file "$STEIMMO_ENV_FILE" \
    --env "DJANGO_SETTINGS_MODULE=$STEIMMO_SETTINGS_MODULE" --env POSTGRES_HOST=postgres \
    --env DJANGO_BOOTSTRAP_ON_START=0 \
    --mount "type=volume,src=$public_volume,dst=/app/staticfiles,volume-subpath=releases/one" "$image" sh -ec \
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
docker run --rm --network "container:$caddy" --entrypoint python "$image" -c '
import json, sys, urllib.error, urllib.request
class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args):
        return None
opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
request = urllib.request.Request(sys.argv[1] + "/health/", headers={"Host": "localhost", "X-Forwarded-Proto": "https"})
with opener.open(request, timeout=5) as response:
    assert json.load(response) == {"service": "steimmo", "status": "ok"}
try:
    opener.open(urllib.request.Request(sys.argv[1] + "/", headers={"Host": "localhost"}), timeout=5)
    raise AssertionError("HTTP did not redirect")
except urllib.error.HTTPError as error:
    assert error.code == 301 and error.headers["Location"].startswith("https://")
' "http://$proxy_host:8010"
caddy_ca=$(docker exec "$caddy" cat /data/caddy/pki/authorities/local/root.crt)
https_check() {
    printf '%s\n' "$caddy_ca" | docker run --rm --interactive --network "container:$caddy" \
        --entrypoint python "$image" -c '
import json, ssl, sys, urllib.error, urllib.request
context = ssl.create_default_context(cadata=sys.stdin.read())
opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), urllib.request.HTTPSHandler(context=context))
def get(path):
    with opener.open("https://localhost" + path, timeout=10) as response:
        assert response.status == 200
        return response.read()
assert json.loads(get("/health/")) == {"service": "steimmo", "status": "ok"}
assert get("/")
css = get("/static/css/app.css")
assert css == b"release two\n" if sys.argv[1] == "new" else css and css != b"release two\n"
assert get("/static/admin/css/base.css")
for path in ("/media/smoke.txt", "/static/../shared/.env"):
    try:
        get(path)
        raise AssertionError(path + " was public")
    except urllib.error.HTTPError as error:
        assert error.code == 404
' "$1"
}
https_check original
if [[ $mode == demo ]]; then
    printf '%s\n' "$caddy_ca" | docker run --rm --interactive --network "container:$caddy" \
        --entrypoint python "$image" /app/ops/demo-smoke.py https://localhost
fi
docker exec "$caddy" sh -ec \
    'test ! -e /srv/steimmo/shared; test ! -e /srv/steimmo/backups; if touch /srv/steimmo/public/write-check 2>/dev/null; then exit 1; fi'
# The same read-only mount must see an atomic asset switch and its rollback.
docker run --rm --user 0:0 --entrypoint sh --volume "$public_volume:/out" "$image" -ec \
    'cp -a /out/releases/one /out/releases/two; printf "release two\n" > /out/releases/two/css/app.css; ln -s releases/two /out/.next; mv -Tf /out/.next /out/current'
https_check new
docker run --rm --user 0:0 --entrypoint sh --volume "$public_volume:/out" "$image" -ec \
    'ln -s releases/one /out/.next; mv -Tf /out/.next /out/current'
https_check original
compose up --detach --no-build --force-recreate --wait --wait-timeout 120 web
compose exec -T web python -c \
    'from pathlib import Path; assert Path("/app/media/smoke.txt").read_text() == "persistent"'
printf 'Container-Smoke-Test (%s) mit Docker-Caddy, TLS, Static-Wechsel und Restore erfolgreich.\n' "$mode"
