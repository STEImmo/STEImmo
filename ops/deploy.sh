#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

fail() { printf '%s\n' "$*" >&2; exit 1; }
[[ $# == 4 ]] || fail 'Aufruf: deploy.sh PROJEKTPFAD RELEASE IMAGE_DIGEST COMMIT'
root=$(realpath -e -- "$1")
release_id=$2
image=$3
commit=$4
[[ $root =~ ^/[a-zA-Z0-9/_-]+$ && $root != / ]] || fail 'Ungültiger Projektpfad.'
[[ $commit =~ ^[a-f0-9]{40}$ ]] || fail 'Ungültiger Commit.'
[[ $release_id =~ ^${commit}-[0-9]+-[0-9]+$ ]] || fail 'Ungültige Release-ID.'
[[ $image =~ ^ghcr\.io/steimmo/steimmo@sha256:[a-f0-9]{64}$ ]] || fail 'Image-Digest fehlt.'
[[ $(uname -m) == aarch64 ]] || fail 'Dieses Deployment benötigt einen ARM64-Server.'
for tool in docker curl flock realpath; do command -v "$tool" >/dev/null || fail "$tool fehlt."; done

env_file="$root/shared/.env"
[[ -f $env_file && ! -L $env_file ]] || fail 'Produktive shared/.env fehlt.'
[[ $(stat -c %a "$env_file") == 600 ]] || fail 'shared/.env benötigt Modus 0600.'
public="$root/public"
[[ -d $public/releases ]] || fail 'public/releases fehlt; Bootstrap erneut ausführen.'
[[ ! -e $public/current || -L $public/current ]] || fail 'public/current muss ein Symlink sein.'
exec 9>"$root/deploy.lock"
flock -n 9 || fail 'Ein Deployment läuft bereits.'
[[ $(df -Pk "$root" | awk 'NR == 2 { print $4 }') -gt 1048576 ]] || fail 'Weniger als 1 GiB frei.'

incoming="$root/incoming/$release_id"
release="$root/releases/$release_id"
[[ $(realpath -e -- "$incoming") == "$incoming" ]] || fail 'Ungültiges Eingangsverzeichnis.'
[[ -f $incoming/compose.prod.yaml && ! -e $release ]] || fail 'Release fehlt oder existiert bereits.'
previous=''
if [[ -e $root/current || -L $root/current ]]; then
    [[ -L $root/current ]] || fail 'current muss ein symbolischer Link sein.'
    previous=$(realpath -e -- "$root/current")
    [[ $previous == "$root/releases/"* && -f $previous/success ]] || fail 'Ungültiger Vorgänger.'
    [[ -d $public/releases/${previous##*/} ]] || fail 'Öffentliche Assets des Vorgängers fehlen; Bootstrap erneut ausführen.'
fi
mkdir -p "$root/releases" "$root/backups"
chmod 755 "$root" "$root/releases"
chmod 700 "$root/backups"
mv -- "$incoming" "$release"
chmod 755 "$release"
printf '%s\n' "$image" > "$release/image.txt"

compose_at() {
    local directory=$1
    shift
    env -u POSTGRES_DB -u POSTGRES_USER -u POSTGRES_PASSWORD \
        STEIMMO_IMAGE="$(cat "$directory/image.txt")" STEIMMO_ENV_FILE="$env_file" \
        docker compose --project-name steimmo --env-file "$env_file" \
        --file "$directory/compose.prod.yaml" "$@"
}
compose() { compose_at "$release" "$@"; }
phase=preflight
stopped=0
migration_started=0
schema_changes=1
switched=0
success=0

switch_current() {
    ln -s -- "$1" "$root/.current-$release_id"
    mv -Tf -- "$root/.current-$release_id" "$root/current"
    ln -s -- "releases/${1##*/}" "$public/.current-$release_id"
    mv -Tf -- "$public/.current-$release_id" "$public/current"
}

on_exit() {
    local code=$?
    trap - EXIT
    set +e
    if (( success == 0 )); then
        printf 'Deployment fehlgeschlagen in Phase %s (Exit %s).\n' "$phase" "$code" >&2
        if (( switched == 1 )); then
            if [[ -n $previous ]]; then
                switch_current "$previous"
            elif [[ -L $root/current && $(readlink "$root/current") == "$release" ]]; then
                unlink "$root/current"
            fi
            if [[ -z $previous && -L $public/current && $(readlink "$public/current") == "releases/$release_id" ]]; then
                unlink "$public/current"
            fi
        fi
        if (( stopped == 1 )); then
            compose stop web || true
            if [[ -n $previous ]] && (( migration_started == 0 || schema_changes == 0 )); then
                printf 'Stelle vorheriges Image mit unverändertem Schema wieder her.\n' >&2
                compose_at "$previous" up --detach --no-build --no-deps --wait --wait-timeout 120 web || true
            else
                printf 'Webdienst bleibt angehalten; Schema und Backup administrativ prüfen.\n' >&2
            fi
        fi
    fi
    exit "$code"
}
trap on_exit EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

printf 'Lade Release %s.\n' "$release_id"
compose config --quiet
compose pull web
[[ $(docker image inspect "$image" --format '{{.Architecture}}') == arm64 ]] || fail 'Falsche Image-Architektur.'
[[ $(docker image inspect "$image" --format '{{ index .Config.Labels "org.opencontainers.image.revision" }}') == "$commit" ]] || fail 'Image und Commit stimmen nicht überein.'

# Reject placeholder settings before the first database is initialized.
compose run --rm --no-deps -T web python manage.py check --deploy --fail-level WARNING

# Never recreate a running database during an application release.
if [[ -z $(compose ps --status running --quiet postgres) ]]; then
    compose up --detach --no-build --wait --wait-timeout 120 postgres
fi
if compose run --rm --no-deps -T web python manage.py deployment_preflight \
    > "$release/preflight.log" 2>&1; then
    schema_changes=0
else
    status=$?
    [[ $status == 3 ]] || fail "Produktionsprüfung fehlgeschlagen; siehe $release/preflight.log."
fi

phase=backup
stopped=1
compose stop web
backup="$root/backups/$release_id"
mkdir -- "$backup"
compose exec -T postgres sh -ec 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" --format=custom' \
    > "$backup/database.dump"
[[ -s $backup/database.dump ]] || fail 'Leere Datenbanksicherung.'
compose exec -T postgres pg_restore --list < "$backup/database.dump" > /dev/null
compose run --rm --no-deps -T web tar -C /app/media -czf - . > "$backup/media.tar.gz"
[[ -s $backup/media.tar.gz ]] || fail 'Leere Media-Sicherung.'
tar -tzf "$backup/media.tar.gz" > /dev/null
printf 'Backup vollständig.\n' > "$backup/complete"

phase=migration
migration_started=1
compose run --rm --no-deps -T web python manage.py migrate --noinput

phase=static
static="$public/releases/$release_id"
mkdir -- "$static"
chmod 755 "$static"
docker run --rm --user 0:0 --entrypoint sh \
    --mount "type=bind,src=$static,dst=/out" "$image" \
    -ec 'chown 10001:10001 /out; chmod 755 /out'
compose run --rm --no-deps -T --volume "$static:/app/staticfiles" \
    web python manage.py collectstatic --noinput

phase=start
compose up --detach --no-build --no-deps --wait --wait-timeout 120 web
switched=1
switch_current "$release"

phase=https
public_url=https://steimmo-projekt-page.justus.software
curl --fail --silent --show-error --retry 3 --retry-delay 2 --max-time 15 \
    "$public_url/health/" > "$release/health.json"
docker run --rm --interactive --entrypoint python "$image" -c \
    'import json,sys; sys.exit(json.load(sys.stdin) != {"service":"steimmo","status":"ok"})' \
    < "$release/health.json"
for path in / /static/css/app.css; do
    status=$(curl --fail --silent --show-error --retry 3 --max-time 15 \
        --output /dev/null --write-out '%{http_code}' "$public_url$path")
    [[ $status == 200 ]] || fail "HTTPS-Prüfung für $path liefert HTTP $status."
done

printf '{"commit":"%s","image":"%s","previous":"%s","backup":"%s","schema_changes":%s}\n' \
    "$commit" "$image" "$previous" "$backup" "$schema_changes" > "$release/release.json"
date -u +%FT%TZ > "$release/success"
success=1
printf 'Release %s erfolgreich.\n' "$release_id"
