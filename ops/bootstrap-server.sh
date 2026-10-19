#!/usr/bin/env bash
# Run once as an administrator on the Ubuntu ARM64 host. Does not modify Caddy or DNS.
set -Eeuo pipefail
[[ $EUID == 0 ]] || { echo 'Als Administrator ausführen.' >&2; exit 1; }
[[ $(uname -m) == aarch64 ]] || { echo 'ARM64 erforderlich.' >&2; exit 1; }
for tool in docker caddy curl flock; do command -v "$tool" > /dev/null; done
user=${1:-deploy}
[[ $user =~ ^[a-z_][a-z0-9_-]*$ ]] || exit 1
id "$user" > /dev/null
root=/srv/steimmo
[[ ! -L $root ]] || { echo 'Projektpfad darf kein Symlink sein.' >&2; exit 1; }
install -d -m 755 -o "$user" -g "$(id -gn "$user")" "$root" "$root/releases"
install -d -m 700 -o "$user" -g "$(id -gn "$user")" "$root/shared" "$root/incoming" "$root/backups"
# Docker access is root-equivalent; ADR-0018 records this deployment model.
usermod -aG docker "$user"
docker volume create steimmo-prod-postgres-data > /dev/null
docker volume create steimmo-prod-media-data > /dev/null
docker network inspect steimmo-prod > /dev/null 2>&1 || docker network create steimmo-prod > /dev/null
printf 'Projekt vorbereitet. Voraussichtliche Docker-NAT-Quelladresse (am Live-Request verifizieren):\n'
docker network inspect steimmo-prod --format '{{range .IPAM.Config}}{{println .Gateway}}{{end}}'
printf 'shared/.env mit Modus 0600 einrichten; Caddy-Snippet prüfen und administrativ integrieren.\n'
printf 'Danach als %s neu anmelden und gegebenenfalls docker login ghcr.io ausführen.\n' "$user"
