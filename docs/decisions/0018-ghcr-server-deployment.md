# ADR-0018: GHCR und Deployment auf einem Ubuntu-ARM-Server

- Status: Angenommen; im Repository implementiert, Servereinrichtung ausstehend
- Datum: 2026-10-19
- Geltungsbereich: STEImmo-Produktion auf einem einzelnen Server

## Kontext und Ziel

Der Django-Monolith soll durch GitHub Actions geprüft, als Docker-Image in
GitHub Container Registry (GHCR) veröffentlicht und über einen eigenen
Deploy-Benutzer auf dem Server aktualisiert werden. Docker Compose betreibt
Gunicorn und PostgreSQL; der vorhandene Caddy-Dienst übernimmt HTTPS,
statische Dateien und die Weiterleitung zur Anwendung.

Vom Betreiber bestätigte Rahmenbedingungen:

| Einstellung | Wert |
|---|---|
| Domain | `steimmo-projekt-page.justus.software` |
| Betriebssystem | Ubuntu, genaue Version noch offen |
| Prozessor | ARM; geplant ist `linux/arm64`, vor Einrichtung mit `uname -m` bestätigen |
| Caddy | Dienst direkt auf dem Server |
| Repository | `STEImmo/STEImmo` gemäß lokalem Git-Remote |
| Release-Branch | `main` gemäß bestehender CI |
| SSH-Server | `178.104.51.71`, Port 22 |
| Deploy-Benutzer | vorhandener Benutzer `deploy` |
| SSH-Anmeldung | Passwort über GitHub-Secret `DEPLOY_SSH_PASSWORD`, auf Betreiberwunsch |
| Projektverzeichnis | Standard: `/srv/steimmo` |
| App-Port | `127.0.0.1:8010`, vor Einrichtung auf Belegung prüfen |

Passwortwert, Ubuntu-Version, DNS-Zugriff und SMTP-Konfiguration
sind vor der Einrichtung zu klären. Der SSH-Hostname kann von der Domain
abweichen. Bei einem weiteren Uni-Proxy oder CDN vor Caddy müssen TLS- und
Proxy-Vertrauen entsprechend angepasst werden.

### Geprüfte Referenz

`VORNISUG/website` liefert über den GitHub-Zugang 404. Das zugängliche
Repository [VORNISUG/VornisWebsite](https://github.com/VORNISUG/VornisWebsite)
wird als mutmaßlich gemeinte Referenz verwendet. Am 2026-10-19 wurden dessen
aktuelle Dateien auf dem Standardbranch gelesen:

- [Workflow](https://github.com/VORNISUG/VornisWebsite/blob/main/.github/workflows/deploy.yml):
  `push` auf `main` und `workflow_dispatch`, Jobs `verify → images → deploy`,
  ARM64-Build, GHCR mit `GITHUB_TOKEN`, SSH und Environment `deploy`.
- [Deploy-Skript](https://github.com/VORNISUG/VornisWebsite/blob/main/ops/deploy.sh):
  Images laden und bestehende Compose-Dienste aktualisieren.
- [Produktions-Compose](https://github.com/VORNISUG/VornisWebsite/blob/main/docker-compose.deploy.yml)
  und [Caddy-Snippet](https://github.com/VORNISUG/VornisWebsite/blob/main/ops/caddy-vornis.caddy):
  Weiterleitung über einen Host-Port.

Das Ablaufmuster wird übernommen. STEImmo erhält genau ein eigenes
Anwendungsimage. PostgreSQL bleibt beim festgelegten `postgres:18.6`.
Directus, Bootstrap-Images, VORNIS-Konfiguration und SEO-Dienste werden für
diesen Monolithen nicht benötigt. Die dort verwendete Adresse `172.17.0.1`
wird durch Loopback ersetzt, weil Caddy hier auf dem Host läuft.

### Ausgangslage vor der Umsetzung

- `.github/workflows/ci.yml` prüft bisher ausschließlich Pull Requests nach
  `main`; ein erfolgreicher PR-Lauf allein prüft den späteren Main-Commit nicht.
- `Dockerfile` startet Gunicorn, installiert aber auch Entwicklungswerkzeuge
  und legt keinen unprivilegierten Laufzeitbenutzer fest.
- `docker/compose.yaml` baut lokal, bindet den App-Port an Loopback und besitzt
  Datenbank-, Media- und Static-Volumes. PostgreSQL hat ebenfalls einen Host-Port.
- `docker/entrypoint.sh` führt bei jedem Start Migrationen und `collectstatic`
  aus. Für kontrollierte Releases müssen diese Schritte einmalig erfolgen.
- `/health/` prüft die Datenbankverbindung. Der derzeitige Container-Check
  muss mit Produktions-Hostnamen und einer späteren HTTPS-Umleitung funktionieren.
- Gunicorn liefert die gesammelten statischen Dateien nicht selbst aus.
  Übergabefotos werden bereits über eine geschützte Django-View ausgeliefert.
- Proxy-HTTPS ist in den Settings berücksichtigt; sichere Cookies,
  HTTPS-Umleitung und verlässlich erforderliche Produktionswerte sind noch
  ausdrücklich zu konfigurieren.

## Entscheidung: Pipeline und Release

~~~mermaid
flowchart LR
    PR[Pull Request] --> CI[Django-Tests und Ruff]
    MAIN[Push auf main] --> VERIFY[Prüfung des Main-Commits]
    VERIFY --> BUILD[ARM64-Image bauen]
    BUILD --> GHCR[GHCR: SHA-Tag und Digest]
    GHCR --> SSH[SSH als deploy]
    SSH --> RELEASE[Backup, Migration, Containerstart]
    RELEASE --> HEALTH[Healthcheck und HTTPS-Prüfung]
~~~

### 1. Prüfen

Die vorhandenen Prüfungen bleiben für PRs erhalten und werden für denselben
Commit vor dem Main-Release ausgeführt: Python 3.13, PostgreSQL 18.6,
Django-Systemcheck, Migrationsprüfung, Django-Tests, Ruff-Lint und
Formatprüfung sowie Docker-Build und Compose-Validierung. Produktions-Compose
wird zusätzlich mit fiktiven Werten geprüft; Konfiguration mit echten Secrets
darf nicht in CI-Ausgaben landen.

Die gemeinsamen Prüfschritte werden wiederverwendet, etwa als aufrufbarer
CI-Workflow. `deploy.yml` ruft diese Prüfung auf und verknüpft die folgenden
Jobs ausdrücklich über `needs`. Ein Deploy über `workflow_dispatch` ist nur
vom Branch `main` zulässig und durchläuft dieselben Prüfungen.

### 2. Bauen und in GHCR veröffentlichen

- Image: `ghcr.io/steimmo/steimmo:sha-<vollständiger-commit>`.
- Plattform: `linux/arm64`, gebaut mit Buildx und QEMU auf `ubuntu-latest`.
  Dadurch benötigt das private Repository keinen nativen ARM-Runner.
- Buildx-Cache wie in der Referenz; Actions bei Umsetzung auf geprüfte
  Commit-SHAs festlegen. Produktionsimage enthält keine Ruff-Werkzeuge.
- OCI-Metadaten verknüpfen das Image mit Repository und Commit.
- Der Build gibt den Registry-Digest als Job-Output aus. Deployment und
  Rollback verwenden `ghcr.io/steimmo/steimmo@sha256:<digest>`.
- Der Image-Job lädt anschließend genau diesen Digest und führt den
  Produktions-Smoke-Test unter ARM64-Emulation aus. Erst nach dessen Erfolg
  beginnt der Server-Deploy.
- Nur der Image-Job erhält `packages: write`; allgemeines Tokenrecht bleibt
  `contents: read`. Login erfolgt mit dem temporären `GITHUB_TOKEN`.
- Image als nicht privilegierter Benutzer ausführen. `.dockerignore` um
  lokale Konfiguration, weitere echte Env-Dateien, IDE-, QA- und temporäre
  Dateien ergänzen; keine Produktions-Secrets als Build-Argumente.

GitHub dokumentiert den [GHCR-Login im Workflow](https://docs.github.com/en/actions/tutorials/publish-packages/publish-docker-images)
und das [Laden per Digest](https://docs.github.com/en/packages/working-with-a-github-packages-registry/working-with-the-container-registry).
Ein beweglicher `latest`-Tag ist für die Auswahl eines Releases unnötig.

### 3. Über SSH ausrollen

GitHub Environment `deploy` erlaubt ausschließlich `main`. Wie in der
Referenz gilt eine gemeinsame Produktions-Concurrency-Gruppe mit
`cancel-in-progress: false`; ein laufender Deploy darf bei neuen Commits
nicht unterbrochen werden. Zusätzlich schützt eine Serversperre mit `flock`
vor gleichzeitigen manuellen und automatisierten Releases.

Der Workflow überträgt nur versionierte Betriebsdateien und die Image-Referenz
in ein Releaseverzeichnis. Auf dem Server erfolgt kein Git-Checkout und kein
Image-Build. Die produktive `.env` wird weder übertragen noch überschrieben.

Ablauf im Deploy-Skript, Abbruch bei jedem Fehler:

1. Konfiguration, Digestformat, Architektur, freien Speicher und bestehende
   Release-Metadaten prüfen. Fester Compose-Projektname `steimmo` bei jedem
   Aufruf; vorhandene Datenträger ausdrücklich zuordnen.
2. Neues Image laden und dessen Produktionskonfiguration prüfen. Bei einem
   Registry- oder Konfigurationsfehler bleibt die laufende Version bestehen.
3. PostgreSQL erreichbar halten. Bei der Erstinstallation initial starten;
   spätere App-Releases aktualisieren die Datenbankversion nicht mit.
4. Webdienst für ein kurzes Wartungsfenster anhalten. PostgreSQL-Dump und
   Media-Sicherung erstellen und den erfolgreichen Abschluss prüfen. Ohne
   erfolgreiche Sicherung keine Migration. Die Erstinstallation besitzt
   naturgemäß noch keinen vorherigen Anwendungsstand.
5. Mit dem neuen Image einmalig `migrate --noinput` ausführen. Der
   Produktions-EntryPoint darf dabei keine zusätzlichen Migrationen starten.
6. Mit demselben Image `collectstatic --noinput` in das neue, getrennte
   Release-Staticverzeichnis ausführen. Besitzrechte für den nicht
   privilegierten Containerbenutzer vorbereiten.
7. Gunicorn mit dem Digest starten, mit begrenztem Timeout auf den gesunden
   Container warten. Host-Port ist ausschließlich `127.0.0.1:8010`.
8. Nach erfolgreichem internem Check den Static-Verweis auf das neue Release
   umschalten. Öffentliche Domain über HTTPS auf `/health/`, Startseite und
   eine tatsächliche CSS-Datei prüfen; HTTP-Status und Health-Inhalt auswerten.
9. Erst danach Release als erfolgreich markieren. Commit, Digest,
   Compose-Konfiguration, vorherigen Release und Backup-Zuordnung festhalten.

Die App-Startfunktion startet nur Gunicorn; automatische Migrationen bei
Neustarts entfallen in Produktion. Der lokale Entwicklungsablauf kann sein
bisheriges Verhalten behalten. Compose unterstützt
[das Warten auf gesunde Dienste](https://docs.docker.com/reference/cli/docker/compose/up/).

Bei Fehlschlag bleibt der Workflow rot und meldet die gescheiterte Phase.
Automatisches Zurückstarten des alten Images ist nur bei unverändertem oder
ausdrücklich rückwärtskompatiblem Schema vorgesehen. Bei fehlgeschlagenen
oder inkompatiblen Migrationen bleibt die Anwendung zur Prüfung angehalten.
Datenbank-Restore und rückwärts gerichtete Migrationen erfolgen nach
gesonderter Freigabe; ein Image-Rollback setzt Daten nicht zurück.

## Gemeinsame Prüfung des Django-Schlüssels (Issue #133)

Auch `config.settings` verweigert bei `DEBUG=False` bereits beim Import einen
fehlenden oder unsicheren `DJANGO_SECRET_KEY`; ohne `DJANGO_DEBUG` gilt dieser
Modus ebenfalls. `config.settings_production` verwendet dieselbe Validierung.
Erforderlich sind mindestens 50 Zeichen und 5 unterschiedliche Zeichen ohne
äußere Leerzeichen mitzuzählen. `django-insecure-` als Präfix sowie die
Platzhalterbestandteile `change_me` und `change-this` werden unabhängig von
Groß-/Kleinschreibung abgelehnt. Fehlermeldungen geben den Schlüssel nicht aus.
Diese Mindestprüfung kann Zufälligkeit und Geheimhaltung nicht beweisen:
Für Produktion stets ein eigenes Zufallsgeheimnis erzeugen, beispielsweise mit
`openssl rand -hex 32`, und ausschließlich in der Serverkonfiguration speichern.

Nur ausdrücklich aktiviertes `DJANGO_DEBUG=1` erlaubt den öffentlichen lokalen
Beispielschlüssel und bei fehlendem oder leerem Wert den Entwicklungsfallback.
Die Produktionssettings verbieten diesen Entwicklungsmodus weiterhin.
CI erzeugt je Prüflauf einen flüchtigen Zufallsschlüssel ohne Produktionszugriff.
`core/test_secret_key_settings.py` prüft die Basiskonfiguration in isolierten
Prozessen; `core/test_production_settings.py` sichert die Produktionssettings ab.

## Deploy-Benutzer, Serverdateien und Secrets

Der vorhandene Benutzer `deploy` erhält Zugriff auf das Projektverzeichnis
und Docker. Auf ausdrücklichen Betreiberwunsch erfolgt die SSH-Anmeldung
mit Passwort statt mit einem neuen CI-Schlüssel. Der Passwortwert liegt im
GitHub-Environment `deploy` als Secret `DEPLOY_SSH_PASSWORD`.
`ops/ship.sh` verwendet OpenSSH-Askpass: Das Passwort wird weder Teil der
Kommandozeile noch in eine Datei geschrieben. Der temporäre Helfer enthält
nur den Namen der Umgebungsvariable. Das globale Caddyfile bleibt
administrativ verwaltet; der Deploy-Ablauf ändert es nicht.

Für den einfachen Compose-Betrieb ist die Mitgliedschaft in der Docker-Gruppe
vorgesehen. Das gewährt faktisch Root-Rechte auf dem gesamten Host, auch auf
andere Projekte. Der Benutzername und fehlendes allgemeines `sudo` stellen
keine Sicherheitsgrenze dar. Dieses Betriebsmodell ist Teil der beauftragten
Implementierung. Ist eine solche Trennung erforderlich,
muss stattdessen ein eigener Rootless-Docker-Betrieb geplant werden.
[Docker beschreibt diese Rechte ausdrücklich.](https://docs.docker.com/engine/install/linux-postinstall/)

~~~text
/srv/steimmo/
  shared/
    .env                     # echte Produktionswerte, Modus 0600
  releases/<commit>-<run>/
    compose.prod.yaml
    deploy.sh
    static/                  # nur öffentliche Assets
    image.txt                # gepinnter Digest, wird für Compose verwendet
    release.json             # Commit, Digest, Vorgänger, Backup, keine Secrets
    success                  # erst nach erfolgreichen öffentlichen Prüfungen
  current -> releases/<erfolgreiches-release>
  backups/                   # DB und Media, zugriffsbeschränkt
~~~

Ein Releaseverzeichnis wird nach Erfolg nicht überschrieben. Persistente
PostgreSQL- und Media-Volumes liegen außerhalb der Releaseverzeichnisse.
Caddy erhält Leserechte nur auf öffentliche Static-Dateien samt notwendigen
Verzeichnisrechten, nicht auf `.env`, Backups oder Media. Mindestens der
aktuelle und vorherige erfolgreiche Release bleiben samt Images erhalten.
Keine hostweiten Prune-Befehle im Deployment.

| Ort | Einstellung | Verwendung |
|---|---|---|
| GitHub Environment Secret | `DEPLOY_SSH_PASSWORD` | Passwort des vorhandenen Deploy-Benutzers |
| GitHub Environment Variablen | `DEPLOY_HOST`, `DEPLOY_PORT`, `DEPLOY_USER`, `DEPLOY_PATH` | SSH-Ziel und Projektpfad |
| GitHub Environment Variable | `DEPLOY_KNOWN_HOSTS` | administrativ geprüfter öffentlicher SSH-Hostschlüssel |
| GitHub automatisch | `GITHUB_TOKEN` | Image im Build-Job veröffentlichen |
| Server, Docker-Anmeldung | `GHCR_PULL_USERNAME`, `GHCR_PULL_TOKEN` | bei privatem Package ein PAT classic mit `read:packages` und Package-Zugriff |
| Server, `shared/.env` | Django-, PostgreSQL- und SMTP-Werte | Laufzeitkonfiguration |

Den GHCR-Lesezugang einmalig per `--password-stdin` unter dem Deploy-Benutzer
einrichten; seine lokale Docker-Credential-Datei schützen und den Token
rotieren. Kein Registry-Token als Argument eines SSH-Kommandos. Bei einem
öffentlichen Package ist kein Pull-Token erforderlich. Die
[GHCR-Dokumentation](https://docs.github.com/en/packages/working-with-a-github-packages-registry/working-with-the-container-registry)
beschreibt Scope und Zugriffsrechte.

Der SSH-Hostschlüssel wird über einen vertrauenswürdigen administrativen
Kanal geprüft und fest hinterlegt. Anders als in der Referenz wird nicht bei
jedem Lauf ausschließlich einem ungeprüften `ssh-keyscan` vertraut.

## Produktions-Compose und Django

Eine eigenständig lesbare `docker/compose.prod.yaml` verwendet ausschließlich
Images und feste, projektspezifische Volumes. Das vermeidet geerbte
Development-Einstellungen aus mehreren Overrides. PostgreSQL 18.6 behält
seinen Datenpfad `/var/lib/postgresql` und bekommt keinen Host-Port.
Es laufen genau der Django-Webdienst und PostgreSQL; Caddy bleibt Host-Dienst.
Media ist persistent, Quellcode wird nicht vom Host eingebunden. Docker-Logs
erhalten eine Größen- und Rotationsgrenze.

Für Produktion erforderlich:

- `DJANGO_DEBUG=0`, ein unabhängiger starker `DJANGO_SECRET_KEY` und sichere
  Datenbankzugangsdaten. Fehlende oder bekannte Entwicklungswerte führen
  zum Abbruch, statt auf Defaults zurückzufallen.
- `DJANGO_ALLOWED_HOSTS=steimmo-projekt-page.justus.software` und
  `DJANGO_CSRF_TRUSTED_ORIGINS=https://steimmo-projekt-page.justus.software`.
- Sichere Session- und CSRF-Cookies sowie HTTPS-Umleitung über bewusst
  eingeführte Produktionssettings. HSTS erst nach geprüfter HTTPS-Funktion
  aktivieren; kein pauschales `includeSubDomains` oder Preload.
- `SECURE_PROXY_SSL_HEADER` bleibt auf Caddys `X-Forwarded-Proto` abgestimmt.
  Der interne HTTP-Healthcheck sendet den erlaubten Domain-Host und den
  HTTPS-Proxyheader, damit er weder an `ALLOWED_HOSTS` noch an der Umleitung
  scheitert. Extern wird regulär HTTPS geprüft.
- `DJANGO_LOGIN_THROTTLE_TRUSTED_PROXY_IPS` enthält nur die tatsächlich bei
  Gunicorn ankommende, geprüfte Caddy-Quelladresse. Durch Docker-NAT kann
  dies eine Bridge-Adresse sein, obwohl Caddy `127.0.0.1` anspricht.
  Keine geratenen Adressen oder pauschalen privaten Netze zulassen.
- Produktiven SMTP-Versand einschließlich Registrierung und Mitarbeiter-MFA
  prüfen. Kein Mailpit und kein lokales Entwicklungskonto in Produktion.
- `check --deploy` ausführen und Meldungen gezielt beheben bzw. eine bewusste
  HSTS-Einführung dokumentieren. Zusätzlich betriebliche Pflichtwerte prüfen.

Diese Punkte konkretisieren die
[Django-Deployment-Checkliste](https://docs.djangoproject.com/en/5.2/howto/deployment/checklist/)
für die vorhandenen Settings. Neue Sicherheitsoptionen müssen bei der
Implementierung tatsächlich in den Settings ausgewertet werden; bloße
Einträge in der `.env` bewirken bisher keine Änderung.

## Caddyfile für den Host-Dienst

Geplanter projektbezogener Block im administrativ verwalteten Caddyfile:

~~~caddyfile
steimmo-projekt-page.justus.software {
    encode zstd gzip

    handle_path /static/* {
        root * /srv/steimmo/current/static
        file_server
    }

    handle /media/* {
        respond 404
    }

    handle {
        reverse_proxy 127.0.0.1:8010
    }
}
~~~

Der Static-Pfad enthält ausschließlich das Ergebnis von `collectstatic`.
Geschützte Fotos und Dokumente werden über ihre berechtigungsgeprüften
Django-Routen ausgeliefert; das Media-Volume wird niemals pauschal als
öffentliches Verzeichnis eingebunden.

Caddy setzt die notwendigen Proxyheader standardmäßig selbst. Bei direkter
Erreichbarkeit über die Domain übernimmt Caddy Zertifikate und die
HTTP-zu-HTTPS-Weiterleitung. Dafür müssen DNS-A/AAAA zum Server passen sowie
80/TCP und 443/TCP erreichbar sein. Nur passende IPv6-Einträge veröffentlichen.
8010 und PostgreSQL bleiben von außen geschlossen.
[Proxyverhalten](https://caddyserver.com/docs/caddyfile/directives/reverse_proxy),
[Static-Auslieferung](https://caddyserver.com/docs/caddyfile/directives/file_server)
und [automatisches HTTPS](https://caddyserver.com/docs/automatic-https)
sind in der Caddy-Dokumentation beschrieben.

Ein Administrator integriert und validiert den Block einmalig und lädt
Caddy neu. Normale App-Releases benötigen keinen Caddy-Neustart und keine
Schreibrechte auf andere Sites.

## Umsetzungspakete und Abnahme

| Reihenfolge | Lieferobjekt | Abnahme |
|---|---|---|
| 1 | Produktionssettings, Dockerfile, EntryPoint und `.dockerignore` | ARM64-Image läuft ohne Root, ohne Dev-Konto und ohne eingebaute Secrets; Healthcheck funktioniert mit HTTPS-Einstellungen |
| 2 | `docker/compose.prod.yaml` und produktive Env-Beispieldatei | nur GHCR-Image, isolierte Persistenz, kein DB-Host-Port, keine Dev-Bind-Mounts; Compose validiert |
| 3 | `ops/deploy.sh` mit Release-Metadaten und Backups | Sperre, fehlgeschlagener Pull, Backupfehler, Migrationfehler und Health-Timeout auf Testinstanz geprüft |
| 4 | wiederverwendbare CI und `.github/workflows/deploy.yml` | PRs prüfen; Main-Commit wird vor Publish und Deploy geprüft; ungültiger Branch darf nicht deployen |
| 5 | administrativer Server-Bootstrap und Caddy-Snippet | SSH-Schlüssel geprüft, Registry-Pull möglich, TLS gültig, Static öffentlich und Media geschützt |
| 6 | erster freigegebener Testrelease und Rückkehr zur Vorgängerversion | identischer Digest, Daten und Uploads bleiben erhalten; Backup-Restore separat auf Testdaten geprüft |

Die Implementierung wurde am 2026-10-19 beauftragt. Die Serveranmeldung als
`deploy` wurde versucht; der Zugang lehnte die vorhandenen SSH-Schlüssel ab.
Der Betreiber wünscht Passwortanmeldung und die Ablage als GitHub-Secret.
Ohne den tatsächlichen Passwortwert wurden weder ein Secret befüllt noch
Serveränderungen vorgenommen. Der Workflow deployt nach Einrichtung jeden
erfolgreich geprüften Push auf `main` automatisch.

### Einmalige Inbetriebnahme

Die folgenden Schritte erfordern Administratorzugriff auf den Zielserver:

1. Docker Engine mit Compose-Plugin und Caddy müssen bereits installiert
   sein. ARM64 mit `uname -m` und den freien Port 8010 prüfen. Danach
   `sudo bash ops/bootstrap-server.sh deploy` ausführen. Das Skript richtet
   ausschließlich Projektverzeichnisse, Docker-Zugriff, zwei benannte Volumes
   und das externe Netzwerk `steimmo-prod` ein. Es ändert kein Caddyfile.
2. `docker/.env.prod.example` nach `/srv/steimmo/shared/.env` kopieren,
   Eigentümer `deploy` und Modus `0600` setzen. Alle Platzhalter ersetzen.
   Für Django und PostgreSQL getrennte, zufällige Geheimnisse verwenden,
   etwa jeweils die Ausgabe von `openssl rand -hex 32`. SMTP-Host,
   Absender und gegebenenfalls SMTP-Zugangsdaten ergänzen.
3. Die von Bootstrap ausgegebene Gateway-IP des Netzwerks als Ausgangspunkt
   für `DJANGO_LOGIN_THROTTLE_TRUSTED_PROXY_IPS` verwenden. Beim Testrequest
   die bei Gunicorn ankommende Quelladresse verifizieren; insbesondere
   prüfen, dass getrennte Clients nicht denselben Throttle-Fingerprint
   erhalten und manipulierte `X-Forwarded-For`-Header nicht durchgereicht werden.
4. Neu als `deploy` anmelden, damit die Docker-Gruppe wirksam wird. Bei
   privatem GHCR-Package unter diesem Benutzer einmalig `docker login
   ghcr.io --username <GitHub-Benutzer> --password-stdin` mit einem Token
   mit `read:packages` ausführen. Der Token benötigt Package-Leserechte und
   gegebenenfalls eine SSO-Freigabe. Er verbleibt ausschließlich auf dem Server.
5. DNS-A-Eintrag der Domain auf `178.104.51.71` setzen bzw. prüfen. Das
   vorhandene Caddyfile um `ops/caddy-steimmo.caddy` ergänzen, bestehende
   Sites erhalten. Mit `sudo caddy validate --config /etc/caddy/Caddyfile`
   prüfen und danach `sudo systemctl reload caddy` ausführen. Erst ein
   erfolgreicher Release erzeugt das Ziel für den Static-Verweis `current`.
6. Im GitHub-Repository das Environment `deploy` auf Branch `main`
   beschränken. Secret `DEPLOY_SSH_PASSWORD` mit dem tatsächlichen
   Serverpasswort anlegen. Variable `DEPLOY_KNOWN_HOSTS` mit dem unabhängig
   geprüften Hostschlüssel setzen. `DEPLOY_HOST=178.104.51.71`,
   `DEPLOY_PORT=22`, `DEPLOY_USER=deploy` und `DEPLOY_PATH=/srv/steimmo`
   sind bereits Workflow-Defaults und können als Environment-Variablen
   überschrieben werden. Bei abweichendem Projektpfad auch Caddys Static-Pfad
   anpassen.
7. Änderungen regulär nach `main` übernehmen bzw. dort den Workflow
   manuell starten. Erst danach gilt der Betrieb als eingerichtet. SMTP,
   Mitarbeiter-MFA, geschützte Fotos, Backup und die tatsächliche
   Client-IP-Erkennung auf der Zielumgebung prüfen. HSTS kann anschließend
   über `DJANGO_SECURE_HSTS_SECONDS` aktiviert werden.

`bash ops/smoke.sh <lokales-runtime-image>` prüft eine frische
Produktionsdatenbank, Produktionssettings, den nicht privilegierten Benutzer,
Static-Sammlung, Datenbank- und Media-Restore, HTTPS-Weiterleitung, Healthcheck
und die Persistenz nach Neuerstellung des Webcontainers. Alle dafür erzeugten
Ressourcen besitzen eigene Namen und werden nach dem Test entfernt. Dieser Test ist Teil der wiederverwendbaren
CI. `python -m unittest discover -s ops/tests -v` prüft zusätzlich Fehlerfälle
des echten Deploy-Skripts mit simulierten Docker- und HTTPS-Antworten.

### Validierung am 2026-10-19

- 144 Django-Tests sowie 14 Deploy-, SSH- und EntryPoint-Tests erfolgreich.
- Django-Systemcheck und Migrationsprüfung erfolgreich; keine neuen
  Datenbankmigrationen erforderlich.
- Ruff-Lint und Formatprüfung, Actionlint, ShellCheck und Caddy-Validierung
  erfolgreich; `git diff --check` ohne Fehler.
- Produktionsimage für `linux/arm64` gebaut und unter lokaler ARM-Emulation
  mit PostgreSQL 18.6 geprüft: Migrationen, Produktionscheck, 131 gesammelte
  Static-Dateien, Datenbank- und Media-Restore, HTTPS-Weiterleitung,
  Healthcheck und erhaltene Uploads nach Container-Neuerstellung erfolgreich.
- Der Produktionscheck berücksichtigt die dokumentiert aufgeschobene
  HSTS-Aktivierung. Sein HTTP-Aufruf hat drei Sekunden Timeout; der
  Container erlaubt zusätzlich Zeit für den Start des Prüfprozesses.
- Die öffentliche Live-Prüfung steht aus: Der SSH-Passwortwert liegt nicht
  vor, und die Domain hatte bei der DNS-Prüfung noch keinen A-Eintrag.
  Server- und GitHub-Secrets wurden nicht verändert.

Für den Betrieb gehören eine regelmäßige Sicherung von PostgreSQL und Media,
eine geschützte Kopie außerhalb dieses Servers sowie ein geprüfter Restore
zur Abnahme. Aufbewahrung und Zeitplan werden vor dem ersten produktiven
Datenbestand festgelegt. Ein persistentes Volume ersetzt kein Backup.

## Konsequenzen und verworfene Alternativen

Das Verfahren bleibt beim beschlossenen Monolithen und vorhandenen Stack.
Releases sind über Commit und Digest nachvollziehbar; der Server benötigt
keine Build-Werkzeuge. Das MVP akzeptiert ein kurzes Wartungsfenster bei
Releases; Blue/Green oder Kubernetes hätten dafür keinen belegten Nutzen.

Ein eigener Caddy-Container würde die bestehende Host-Infrastruktur
duplizieren. Eine zusätzliche Python-Static-Bibliothek entfällt, weil Caddy
die öffentlichen Assets bereits bedienen kann. Ein vollständiger
VORNIS-Compose-Stack würde unnötige Anwendungen und Abhängigkeiten einführen.
Ein Image-Rollback ohne Prüfung der Datenbankschema-Kompatibilität ist kein
verlässliches Wiederherstellungsverfahren.

Dieses ADR ist die zentrale Deployment-Dokumentation. Die README enthält
einen kurzen Verweis; ein paralleles Deployment-Konzept wird nicht geführt.
