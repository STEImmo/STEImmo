"""Verify the demo accounts over real HTTPS, including CSRF and management MFA."""

import http.cookiejar
import re
import ssl
import sys
import urllib.parse
import urllib.request

base = sys.argv[1].rstrip("/")
context = ssl.create_default_context(cadata=sys.stdin.read() or None)


def browser():
    return urllib.request.build_opener(
        urllib.request.ProxyHandler({}),
        urllib.request.HTTPSHandler(context=context),
        urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()),
    )


def submit(opener, path, data):
    url = base + path
    with opener.open(url, timeout=20) as response:
        page = response.read().decode()
    token = re.search(r'name="csrfmiddlewaretoken" value="([^"]+)"', page)
    assert token, "CSRF field missing"
    request = urllib.request.Request(
        url,
        data=urllib.parse.urlencode(data | {"csrfmiddlewaretoken": token[1]}).encode(),
        headers={"Referer": url},
    )
    with opener.open(request, timeout=20) as response:
        assert response.status == 200
        return urllib.parse.urlparse(response.url).path


applicant = browser()
assert submit(applicant, "/accounts/login/", {"username": "user", "password": "user"}) == (
    "/uebergaben/bewerbung/meine/"
)
manager = browser()
assert (
    submit(manager, "/accounts/login/", {"username": "verwaltung", "password": "verwaltung"})
    == "/accounts/mitarbeiter-mfa/"
)
assert submit(manager, "/accounts/mitarbeiter-mfa/", {"code": "000000"}) == "/verwaltung/wohnungen/"
with manager.open(base + "/verwaltung/benutzer/", timeout=20) as response:
    assert response.status == 200
    assert urllib.parse.urlparse(response.url).path == "/verwaltung/benutzer/"
print("Demo-HTTPS-Login für Bewerber und Verwaltung erfolgreich.")
