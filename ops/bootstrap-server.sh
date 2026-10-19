#!/usr/bin/env bash
# Run once as root on Ubuntu ARM64. Caddy runs in its existing Docker container.
set -Eeuo pipefail
[[ $EUID == 0 ]] || { echo 'Als Administrator ausführen.' >&2; exit 1; }
[[ $(uname -m) == aarch64 ]] || { echo 'ARM64 erforderlich.' >&2; exit 1; }
for tool in docker curl flock; do command -v "$tool" > /dev/null; done
docker compose version > /dev/null
user=${1:-deploy}
[[ $user =~ ^[a-z_][a-z0-9_-]*$ ]] || exit 1
id "$user" > /dev/null
root=/srv/steimmo
[[ ! -L $root ]] || { echo 'Projektpfad darf kein Symlink sein.' >&2; exit 1; }
install -d -m 755 -o "$user" -g "$(id -gn "$user")" \
    "$root" "$root/releases" "$root/public" "$root/public/releases"
install -d -m 700 -o "$user" -g "$(id -gn "$user")" "$root/shared" "$root/incoming" "$root/backups"
# Docker access is root-equivalent; ADR-0018 records this deployment model.
usermod -aG docker "$user"
docker volume create steimmo-prod-postgres-data > /dev/null
docker volume create steimmo-prod-media-data > /dev/null
docker network inspect steimmo-prod > /dev/null 2>&1 || docker network create steimmo-prod > /dev/null
# Preserve public assets when upgrading a successful release from the host-Caddy layout.
if [[ -L $root/current && ! -e $root/public/current && ! -L $root/public/current ]]; then
    previous=$(realpath -e -- "$root/current")
    [[ $previous == "$root/releases/"* && -f $previous/success ]] || exit 1
    previous_id=${previous##*/}
    if [[ -d $previous/static && ! -e $root/public/releases/$previous_id ]]; then
        cp -a -- "$previous/static" "$root/public/releases/$previous_id"
    fi
    [[ -d $root/public/releases/$previous_id ]] || exit 1
    runuser -u "$user" -- ln -s -- "releases/$previous_id" "$root/public/current"
fi
printf 'Projekt vorbereitet. shared/.env mit Modus 0600 einrichten.\n'
printf 'Proxy-Quelladresse mit ops/proxy-source.sh messen; keine Gateway-IP raten.\n'
printf 'Caddy benötigt ausschließlich /srv/steimmo/public als Read-only-Mount.\n'
printf 'Danach als %s neu anmelden und gegebenenfalls docker login ghcr.io ausführen.\n' "$user"
