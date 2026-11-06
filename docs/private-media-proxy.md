# Private Medienpfade über den lokalen Reverse Proxy (#140)

## Umfang

Nachweis für [Issue #140](https://github.com/STEImmo/STEImmo/issues/140),
ergänzend zu den Zugriffsmatrizen für
[Bewerbungsdokumente](application-document-access.md), [Fotos](photo-access.md)
und [PDFs/Exporterstellung](pdf-access.md).

Geprüft wird gemäß Auftrag **localhost**: Ein kurzlebiger Caddy 2.10.2 nimmt
echte HTTPS-Anfragen entgegen und leitet an die bestehende lokale
Django-Anwendung auf `127.0.0.1:8000` weiter. Dies ist eine Prüfung über einen
tatsächlich laufenden Reverse Proxy, kein Django-Testclient. Der Nachweis
gilt für diesen lokalen Aufbau und die geprüfte Repository-Konfiguration;
eine abweichend installierte entfernte Serverkonfiguration ist damit nicht abgenommen.

## Reproduzierbarer Prüfaufruf

Bei laufender lokaler Entwicklungsumgebung unter Docker Desktop:

```text
python ops/check_private_media.py --web-container docker-web-1
```

Der Aufruf benötigt nur Python-Standardbibliothek und Docker CLI. Der lokale
Docker-Endpunkt und die ausschließliche Bindung des Upstreams an
`127.0.0.1:8000` werden vor der Dateierstellung geprüft. Remote-Docker-Endpunkte
werden abgewiesen. Das bereits im Projekt verwendete Image `caddy:2.10.2`
muss lokal verfügbar sein.

Der Prüfer lädt `ops/caddy-steimmo.caddy`. Ausschließlich Domain, lokales
Upstream-Ziel und interne TLS-Ausstellung werden für den Test angepasst:

- Domain `localhost` statt der Deployment-Domain;
- Upstream `host.docker.internal:8000` für Docker Desktop;
- `tls internal` für das lokale Zertifikat.

Die Regel `handle /media/* { respond 404 }` und die übrigen Routen bleiben
erhalten. Der Test-Proxy bindet seinen zufällig vergebenen HTTPS-Port nur an
`127.0.0.1`. Der Client prüft Zertifikatskette und Hostnamen anhand der
kurzlebigen Caddy-CA; diese wird nicht im Windows-Zertifikatsspeicher installiert.

## Testdateien und Positivkontrollen

Im tatsächlichen `MEDIA_ROOT` des lokalen Webcontainers werden acht kleine,
eindeutig markierte Dateien exklusiv angelegt. Sie verwenden die aktuellen
Speicherpfadformen, aber eigene zufällige Lauf-UUIDs. Es werden weder
vorhandene Dateien überschrieben noch Konten oder Fachdatensätze angelegt.
Die Dateien enthalten ausschließlich künstliche Markerbytes; sie müssen
für diese Dateiserver-Grenzprüfung keine echten PDF-/Bildinhalte enthalten.

| Dateiklasse | Pfadform unter `/media/` |
|---|---|
| Einkommen | `bewerbungen/<uuid-hex>/einkommen/<uuid-hex>` |
| Identität | `bewerbungen/<uuid-hex>/identitaet/<uuid-hex>` |
| Bonität | `bewerbungen/<uuid-hex>/bonitaet/<uuid-hex>` |
| Übergabefoto | `u/<protokoll-hex>/<pruefpunkt-hex>/<foto-hex>` |
| Wohnungsfoto | `apartments/<uuid>/<foto-hex>.jpg` |
| PDF-Archiv | `private/handovers/<uuid>/<export-hex>/protokoll.pdf` |
| Mieterunterschrift | `private/handovers/<uuid>/<export-hex>/mieter.png` |
| Mitarbeiterunterschrift | `private/handovers/<uuid>/<export-hex>/mitarbeiter.png` |

Alle acht Dateien werden im Webcontainer vor und nach den HTTP-Abrufen gelesen
und auf unveränderte Marker und SHA-256 geprüft. Dadurch kann eine fehlende
Datei nicht versehentlich einen erfolgreichen Sperrnachweis ergeben.
Zusätzlich müssen beide Positivkontrollen erfolgreich sein:

- `/health/`: HTTP 200 mit dem erwarteten STEImmo-Healthcheck;
- `/static/css/app.css`: HTTP 200 direkt von Caddy, bytegenau das öffentliche
  CSS aus dem eingebundenen lokalen Static-Verzeichnis.

## HTTP-Prüfung

Jede vorhandene Testdatei wird anonym mit GET und HEAD über vier Pfadformen
angefragt: normaler Medienpfad, Query-String, kodiertes `m` in `/media/` und
`/static/../media/`. Das ergibt **64 echte HTTPS-Anfragen**.

Für alle Abrufe ist HTTP 404 erforderlich. Weiterleitungen, 403, 500 oder
Netzwerkfehler gelten nicht als bestandene Prüfung. Bei kanonischen Pfaden
werden zusätzlich `Server: Caddy` und ein leerer Body verlangt: Ein bloßes
Django-404 reicht nicht. Markerbytes dürfen auch nicht in einer Fehlerseite
auftauchen. Die vom Prüfer erzeugte JSON-Ausgabe enthält Pfade, Methoden,
Statuscodes, Dateihashes und die beiden Positivkontrollen.

Die Caddy-Mounts werden ebenfalls geprüft: Genau ein Host-Bind-Mount für die
öffentlichen Static-Dateien, schreibgeschützt unter
`/srv/steimmo/public/current`. Das private Medienverzeichnis ist nicht eingebunden.
Die anonymen Caddy-Volumes dienen ausschließlich der temporären Testkonfiguration
und TLS-CA.

Die Rollenprüfung der geschützten Anwendungs-Downloads ist separat durch die
49 Zugriffstests abgesichert. Die Proxy-Prüfung benutzt keine Anwendungskonten
oder Sitzungs-Cookies; die geprüfte Caddy-Medienregel ist unabhängig von Cookies.

## Bereinigung und Sicherheit des Prüfers

Auch bei fehlgeschlagenen Abrufen läuft die Bereinigung. Vor der Entfernung
werden alle Datei-Marker geprüft; eine geänderte Datei wird nicht gelöscht.
Entfernt werden nur die acht eigenen Dateien und leere laufbezogene
Unterverzeichnisse. Gemeinsame Verzeichnisse und vorhandene Daten bleiben erhalten.
Der Container wird vor dem Entfernen über seine eindeutige Laufkennzeichnung
identifiziert; ausschließlich seine anonymen Test-Volumes werden mit entfernt.

`ops/tests/test_private_media.py` prüft insbesondere falsche Erfolgsmeldungen,
Offenlegung in Fehlerseiten, Remote-Docker-Abweisung, unerwartete öffentliche
Upstream-Bindungen, Überschreibschutz, geänderte Marker und die Begrenzung der
Verzeichnisbereinigung. Die Tests laufen durch den vorhandenen CI-Schritt
`python -m unittest discover -s ops/tests -v` mit.

## Ergebnis und Grenzen

Abschließender Durchlauf am 06.11.2026:

| Merkmal | Beobachtetes Ergebnis |
|---|---|
| Laufkennung | `9ca952b1-7b27-4be0-9c0e-59d1650f80b1` |
| temporärer HTTPS-Endpunkt | `https://localhost:51918` — nach der Prüfung entfernt |
| vorhandene Markerdateien | 8, vor und nach den HTTP-Abrufen vollständig und unverändert gelesen |
| HTTP-Matrix | 64 von 64 Abrufen mit 404; keine Marker ausgeliefert |
| Positivkontrollen | Healthcheck 200; öffentliches CSS 200 und bytegleich |
| TLS | Zertifikatskette und Hostname erfolgreich geprüft |
| Caddy-Dateizugriff | ausschließlich öffentlicher Static-Bind-Mount, schreibgeschützt; kein Media-Mount |
| Bereinigung | alle acht Markerdateien und der Prüfcontainer einschließlich seiner anonymen Volumes entfernt |
| ursprüngliche Entwicklungscontainer | Django und PostgreSQL anschließend weiterhin gesund |

SHA-256 des geprüften, unveränderten Quell-Snippets `ops/caddy-steimmo.caddy`
(mit LF-Zeilenenden):
`5f553e6689a3354bfb33f75355ed2beb164bfe84c095a7c9adeb049a8ba330e5`.
Die vollständige JSON-Ausgabe des lokalen Laufs liegt außerhalb der Versionierung
unter `.venv/steimmo-140-local-media-report.json`; der Prüfaufruf erzeugt sie erneut
auf Standardausgabe. Der zufällige HTTPS-Port ist kein dauerhafter Dienst.

Zusätzlich erfolgreich: **49 Django-Zugriffstests** der drei Teilbereiche gegen
PostgreSQL, **27 Betriebs-/Deploy-Tests** einschließlich der neun Prüfer-Tests,
Django-Systemcheck, Migrationsprüfung, Ruff-Lint, Ruff-Format und
`git diff --check`. Es wurden keine Fachmodelle, Migrationen, vorhandenen
Dateien oder laufenden Anwendungskonfigurationen geändert.

Die lokale Prüfung ergänzt den Anwendungsnachweis zu #140. Vor produktivem
Betrieb ist auf der Zielinstallation zu bestätigen, dass dieselbe Medienregel
und Mount-Trennung tatsächlich aktiv sind. Danach folgen die gemeinsame
Abnahme der Akzeptanzkriterien sowie Review und Merge. Der Prüfaufruf führt
keinen Push, kein Deployment und keine PR-/Issue-Aktionen aus.
