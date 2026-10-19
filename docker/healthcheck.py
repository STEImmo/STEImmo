"""Check Gunicorn through its private port using the production host and scheme."""

import json
import os
import urllib.request

host = os.environ["DJANGO_ALLOWED_HOSTS"].split(",")[0].strip()
request = urllib.request.Request(
    "http://127.0.0.1:8000/health/",
    headers={"Host": host, "X-Forwarded-Proto": "https"},
)
with urllib.request.urlopen(request, timeout=3) as response:
    if response.status != 200 or json.load(response) != {"service": "steimmo", "status": "ok"}:
        raise SystemExit("Ungesunder Anwendungsdienst")
