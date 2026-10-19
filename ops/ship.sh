#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

: "${DEPLOY_HOST:?DEPLOY_HOST fehlt}"
: "${DEPLOY_SSH_PASSWORD:?GitHub-Secret DEPLOY_SSH_PASSWORD fehlt}"
: "${DEPLOY_KNOWN_HOSTS:?DEPLOY_KNOWN_HOSTS fehlt}"
: "${STEIMMO_IMAGE:?STEIMMO_IMAGE fehlt}"
: "${GITHUB_SHA:?GITHUB_SHA fehlt}"
: "${GITHUB_RUN_ID:?GITHUB_RUN_ID fehlt}"
: "${GITHUB_RUN_ATTEMPT:?GITHUB_RUN_ATTEMPT fehlt}"
DEPLOY_USER=${DEPLOY_USER:-deploy}
DEPLOY_PORT=${DEPLOY_PORT:-22}
DEPLOY_PATH=${DEPLOY_PATH:-/srv/steimmo}
[[ $DEPLOY_HOST =~ ^[a-zA-Z0-9.-]+$ && $DEPLOY_HOST != -* ]]
[[ $DEPLOY_USER =~ ^[a-z_][a-z0-9_-]*$ ]]
[[ $DEPLOY_PORT =~ ^[0-9]+$ && $DEPLOY_PORT -gt 0 && $DEPLOY_PORT -le 65535 ]]
[[ $DEPLOY_PATH =~ ^/srv/[a-zA-Z0-9/_-]+$ ]]
[[ $GITHUB_SHA =~ ^[a-f0-9]{40}$ ]]
[[ $GITHUB_RUN_ID =~ ^[0-9]+$ && $GITHUB_RUN_ATTEMPT =~ ^[0-9]+$ ]]
[[ $STEIMMO_IMAGE =~ ^ghcr\.io/steimmo/steimmo@sha256:[a-f0-9]{64}$ ]]

ssh_dir=$(mktemp -d)
trap 'rm -rf -- "$ssh_dir"' EXIT
printf '%s\n' "$DEPLOY_KNOWN_HOSTS" > "$ssh_dir/known_hosts"
cat > "$ssh_dir/askpass" <<'ASKPASS'
#!/bin/sh
printf '%s\n' "$DEPLOY_SSH_PASSWORD"
ASKPASS
chmod 700 "$ssh_dir/askpass"
export SSH_ASKPASS="$ssh_dir/askpass" SSH_ASKPASS_REQUIRE=force DISPLAY=steimmo:0
ssh_options=(-o "UserKnownHostsFile=$ssh_dir/known_hosts" -o StrictHostKeyChecking=yes
    -o PreferredAuthentications=password -o PubkeyAuthentication=no
    -o NumberOfPasswordPrompts=1 -o ConnectTimeout=15)
target="$DEPLOY_USER@$DEPLOY_HOST"
release_id="$GITHUB_SHA-$GITHUB_RUN_ID-$GITHUB_RUN_ATTEMPT"
incoming="$DEPLOY_PATH/incoming/$release_id"
setsid --wait ssh -p "$DEPLOY_PORT" "${ssh_options[@]}" "$target" \
    "test -d '$DEPLOY_PATH/shared' && mkdir -m 700 -- '$incoming'" < /dev/null
setsid --wait scp -P "$DEPLOY_PORT" "${ssh_options[@]}" \
    docker/compose.prod.yaml ops/deploy.sh "$target:$incoming/" < /dev/null
setsid --wait ssh -p "$DEPLOY_PORT" "${ssh_options[@]}" "$target" \
    "bash '$incoming/deploy.sh' '$DEPLOY_PATH' '$release_id' '$STEIMMO_IMAGE' '$GITHUB_SHA'" < /dev/null
