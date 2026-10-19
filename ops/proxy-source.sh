#!/usr/bin/env bash
# Measure the peer seen behind Docker's published port, from Caddy's network namespace.
set -Eeuo pipefail
caddy=${1:?Aufruf: proxy-source.sh CADDY_CONTAINER HOST_BRIDGE_IP RUNTIME_IMAGE}
bind_ip=${2:?HOST_BRIDGE_IP fehlt}
image=${3:?RUNTIME_IMAGE fehlt}
connect_host=${4:-$bind_ip}
network=${STEIMMO_NETWORK_NAME:-steimmo-prod}
[[ $caddy != -* && $image != -* ]]
[[ $bind_ip =~ ^([0-9]{1,3}\.){3}[0-9]{1,3}$ ]]
[[ $connect_host =~ ^[a-zA-Z0-9.-]+$ && $connect_host != -* ]]
[[ $(docker inspect --format '{{.State.Running}}' "$caddy") == true ]]
probe=''
cleanup() {
    local status=$?
    trap - EXIT
    if [[ -n $probe ]]; then
        if (( status != 0 )); then docker logs "$probe" >&2 || true; fi
        docker rm --force --volumes "$probe" > /dev/null 2>&1 || true
    fi
    exit "$status"
}
trap cleanup EXIT
probe=$(docker run --detach --network "$network" \
    --publish "$bind_ip::8000" --read-only --cap-drop ALL \
    --security-opt no-new-privileges:true --entrypoint python "$image" -u -c '
from http.server import BaseHTTPRequestHandler, HTTPServer
class Probe(BaseHTTPRequestHandler):
    def do_GET(self):
        body = self.client_address[0].encode("ascii")
        self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
    def log_message(self, *args):
        pass
HTTPServer(("0.0.0.0", 8000), Probe).serve_forever()
')
port=$(docker inspect --format '{{(index (index .NetworkSettings.Ports "8000/tcp") 0).HostPort}}' "$probe")
docker run --rm --network "container:$caddy" --read-only --cap-drop ALL \
    --security-opt no-new-privileges:true --entrypoint python "$image" -c '
import ipaddress, sys, time, urllib.error, urllib.request
deadline = time.monotonic() + 10
opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
while True:
    try:
        with opener.open(sys.argv[1], timeout=1) as response:
            print(ipaddress.ip_address(response.read(64).decode("ascii")))
        break
    except (OSError, urllib.error.URLError):
        if time.monotonic() >= deadline:
            raise
        time.sleep(0.25)
' "http://$connect_host:$port/"
