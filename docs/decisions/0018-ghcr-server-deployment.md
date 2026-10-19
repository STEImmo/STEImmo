# ADR-0018: GHCR und Deployment auf einem Ubuntu-ARM-Server

- Status: Angenommen; im Repository implementiert, Servereinrichtung ausstehend
- Datum: 2026-10-19
- Geltungsbereich: STEImmo-Produktion auf einem einzelnen Server

## Kontext und Ziel

Der Django-Monolith soll durch GitHub Actions geprüft, als Docker-Image in
GitHub Container Registry (GHCR) veröffentlicht und über einen eigenen
Deploy-Benutzer auf dem Server aktualisiert werden. Docker Compose betreibt
Gunicorn und PostgreSQL; der vorhandene Caddy-Container übernimmt HTTPS,
statische Dateien und die Weiterleitung zur Anwendung.

Vom Betreiber bestätigte Rahmenbedingungen:

| Einstellung | Wert |
|---|---|
| Domain | `steimmo-projekt-page.justus.software` |
| Betriebssystem | Ubuntu, genaue Version noch offen |
| Prozessor | ARM; geplant ist `linux/arm64`, vor Einrichtung mit `uname -m` bestätigen |
| Caddy | vorhandener Container `n8n-docker-caddy-1`, Netzwerk `n8n-docker_default` |
| Caddy-Konfiguration | `/root/n8n-docker/Caddyfile` → `/etc/caddy/Caddyfile` |
| Caddy-Compose | `/root/n8n-docker/docker-compose.yml` |
| Repository | `STEImmo/STEImmo` gemäß lokalem Git-Remote |
| Release-Branch | `main` gemäß bestehender CI |
| SSH-Server | `178.104.51.71`, Port 22 |
| Deploy-Benutzer | vorhandener Benutzer `deploy` |
| SSH-Anmeldung | Passwort über GitHub-Secret `DEPLOY_SSH_PASSWORD`, auf Betreiberwunsch |
| Projektverzeichnis | Standard: `/srv/steimmo` |
| App-Port | `172.17.0.1:8010`, über `STEIMMO_BIND_IP` konfiguriert |

Ubuntu-Version und SMTP-Konfiguration sind vor der Einrichtung zu klären.
DNS-A und GitHub-Secret wurden vom Betreiber eingerichtet. Der SSH-Hostname kann von der Domain
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
wird auch hier verwendet: Der Betreiber hat inzwischen bestätigt, dass
Caddy im Container läuft; die frühere Annahme eines Host-Dienstes war falsch.
Die vorhandenen Serverprojekte veröffentlichen ebenfalls an `172.17.0.1`.
Dadurch müssen weder Caddys Netzwerk noch die Netzwerke anderer Projekte
geändert werden. PostgreSQL bleibt ausschließlich im STEImmo-Netzwerk.

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
   Container warten. Host-Port ist an `STEIMMO_BIND_IP` gebunden; auf diesem
   Server an die Docker-Host-Adresse `172.17.0.1`, nicht an alle Interfaces.
8. Nach erfolgreichem internem Check die Verweise `current` und
   `public/current` auf das neue Release bzw. dessen öffentliche Assets
   umschalten. Bei einem Fehler werden beide Verweise zurückgestellt.
   Öffentliche Domain über HTTPS auf `/health/`, Startseite und
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
    image.txt                # gepinnter Digest, wird für Compose verwendet
    release.json             # Commit, Digest, Vorgänger, Backup, keine Secrets
    success                  # erst nach erfolgreichen öffentlichen Prüfungen
  current -> releases/<erfolgreiches-release>
  public/                    # einziger Mount im vorhandenen Caddy-Container
    releases/<commit>-<run>/  # nur collectstatic-Ergebnisse
    current -> releases/<erfolgreiches-release>
  backups/                   # DB und Media, zugriffsbeschränkt
~~~

Ein Releaseverzeichnis wird nach Erfolg nicht überschrieben. Persistente
PostgreSQL- und Media-Volumes liegen außerhalb der Releaseverzeichnisse.
Caddy erhält `/srv/steimmo/public:/srv/steimmo/public:ro`. Der gesamte
Projektpfad wird nicht eingebunden: `.env`, Backups, Media und interne
Release-Dateien bleiben außerhalb dieses Mounts. Der Symlink `public/current`
liegt innerhalb des gemounteten Verzeichnisses und wird bei jedem Release
neu aufgelöst. Ein Mount direkt auf den Symlink würde beim Release-Wechsel
am alten Ziel hängenbleiben. Mindestens der
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
Der STEImmo-Stack enthält genau den Django-Webdienst und PostgreSQL;
der vorhandene Caddy-Container bleibt außerhalb dieses Stacks.
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
  dies die Adresse einer anderen Bridge sein. `ops/proxy-source.sh` misst
  den Peer mit einem kurzlebigen HTTP-Empfänger im STEImmo-Netzwerk hinter
  einem dynamischen Host-Port. Der Client teilt Caddys Netzwerk-Namespace.
  Die Messung verwendet das vorhandene Runtime-Image und entfernt ihre
  eigenen Testcontainer. Weder Caddys `172.18.0.3` noch ein Gateway werden
  ungeprüft übernommen. Keine pauschalen privaten Netze zulassen.
- Produktiven SMTP-Versand einschließlich Registrierung und Mitarbeiter-MFA
  prüfen. Kein Mailpit und kein lokales Entwicklungskonto in Produktion.
- `check --deploy` ausführen und Meldungen gezielt beheben bzw. eine bewusste
  HSTS-Einführung dokumentieren. Zusätzlich betriebliche Pflichtwerte prüfen.

Diese Punkte konkretisieren die
[Django-Deployment-Checkliste](https://docs.djangoproject.com/en/5.2/howto/deployment/checklist/)
für die vorhandenen Settings. Neue Sicherheitsoptionen müssen bei der
Implementierung tatsächlich in den Settings ausgewertet werden; bloße
Einträge in der `.env` bewirken bisher keine Änderung.

## Caddyfile für den vorhandenen Container

Geplanter projektbezogener Block im administrativ verwalteten Caddyfile:

~~~caddyfile
steimmo-projekt-page.justus.software {
    encode zstd gzip

    handle_path /static/* {
        root * /srv/steimmo/public/current
        file_server
    }

    handle /media/* {
        respond 404
    }

    handle {
        reverse_proxy 172.17.0.1:8010
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

Ein Administrator ergänzt im bestehenden Compose-Dienst `caddy` genau
den Read-only-Mount `/srv/steimmo/public:/srv/steimmo/public:ro` und erstellt
ausschließlich diesen Dienst mit `docker compose up -d --no-deps caddy`
neu. Alle vorhandenen Volumes, Netzwerke, Ports und anderen Sites bleiben
erhalten. Danach wird der Site-Block im vorhandenen Caddyfile ergänzt,
innerhalb des Containers validiert und mit `caddy reload` geladen.
Normale App-Releases benötigen keinen Caddy-Neustart und keine
Schreibrechte auf andere Sites. Ports 80 und 443 werden weiterhin nur
vom vorhandenen Caddy veröffentlicht. Die Erreichbarkeit von Port 8010
über die öffentliche Server-IP muss bei der Abnahme ausgeschlossen werden.

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

1. Docker Engine mit Compose-Plugin müssen installiert sein; Caddy läuft
   bereits im vorhandenen Container. ARM64 mit `uname -m` und den freien
   Port 8010 prüfen. Als root `bash ops/bootstrap-server.sh deploy` ausführen.
   Eine Caddy-Binary auf dem Host ist nicht erforderlich. Das Skript richtet
   ausschließlich Projektverzeichnisse, Docker-Zugriff, zwei benannte Volumes
   und das externe Netzwerk `steimmo-prod` ein. Es ändert kein Caddyfile.
   Bei einem vorhandenen erfolgreichen Release im früheren Layout werden
   ausschließlich dessen Static-Dateien ins öffentliche Verzeichnis kopiert.
2. `docker/.env.prod.example` nach `/srv/steimmo/shared/.env` kopieren,
   Eigentümer `deploy` und Modus `0600` setzen. Alle Platzhalter ersetzen.
   Für Django und PostgreSQL getrennte, zufällige Geheimnisse verwenden,
   etwa jeweils die Ausgabe von `openssl rand -hex 32`. SMTP-Host,
   Absender und gegebenenfalls SMTP-Zugangsdaten ergänzen.
3. `STEIMMO_BIND_IP=172.17.0.1` setzen. Das bereits veröffentlichte
   Runtime-Image laden. Erst nach der Caddy-Neuerstellung aus Schritt 5 als root
   `bash ops/proxy-source.sh n8n-docker-caddy-1 172.17.0.1 IMAGE_DIGEST`
   ausführen. Ausschließlich die ausgegebene IP als
   `DJANGO_LOGIN_THROTTLE_TRUSTED_PROXY_IPS` eintragen. Insbesondere
   prüfen, dass getrennte Clients nicht denselben Throttle-Fingerprint
   erhalten und manipulierte `X-Forwarded-For`-Header nicht durchgereicht werden.
4. Neu als `deploy` anmelden, damit die Docker-Gruppe wirksam wird. Bei
   privatem GHCR-Package unter diesem Benutzer einmalig `docker login
   ghcr.io --username <GitHub-Benutzer> --password-stdin` mit einem Token
   mit `read:packages` ausführen. Der Token benötigt Package-Leserechte und
   gegebenenfalls eine SSO-Freigabe. Er verbleibt ausschließlich auf dem Server.
5. DNS-A-Eintrag der Domain auf `178.104.51.71` setzen bzw. prüfen. Das
   vorhandene `/root/n8n-docker/Caddyfile` um den Inhalt von
   `ops/caddy-steimmo.caddy` ergänzen, bestehende Sites erhalten. Vorher
   den oben beschriebenen Public-Mount im Caddy-Compose ergänzen.
   Mit `docker exec n8n-docker-caddy-1 caddy validate --config /etc/caddy/Caddyfile`
   prüfen und danach `docker exec n8n-docker-caddy-1 caddy reload --config /etc/caddy/Caddyfile`
   ausführen. Erst ein
   erfolgreicher Release erzeugt das Ziel für den Static-Verweis `current`.
   Danach die Proxy-Quelladresse aus Schritt 3 messen. Nach jeder späteren
   Neuerstellung Caddys erneut messen und bei geänderter IP die Env sowie
   die Webcontainer aktualisieren.
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

#### Root-Befehle für den bestätigten Server

Erst nach Übernahme dieser Anpassung nach `main` ausführen. Docker und
Compose sind bereits vorhanden. Die Befehle verändern keine bestehenden
Geheimnisse. SMTP muss vom Betreiber konfiguriert werden.

~~~bash
setup_dir=$(mktemp -d)
source_base=https://raw.githubusercontent.com/STEImmo/STEImmo/main
curl -fL "$source_base/ops/bootstrap-server.sh" -o "$setup_dir/bootstrap-server.sh"
curl -fL "$source_base/ops/proxy-source.sh" -o "$setup_dir/proxy-source.sh"
curl -fL "$source_base/ops/caddy-steimmo.caddy" -o "$setup_dir/caddy-steimmo.caddy"
curl -fL "$source_base/docker/.env.prod.example" -o "$setup_dir/.env.prod.example"
bash "$setup_dir/bootstrap-server.sh" deploy

if [ ! -e /srv/steimmo/shared/.env ]; then
    (
        umask 077
        set -o noclobber
        {
            printf 'DJANGO_SECRET_KEY='
            openssl rand -hex 32
            printf 'POSTGRES_PASSWORD='
            openssl rand -hex 32
            sed '/^DJANGO_SECRET_KEY=/d; /^POSTGRES_PASSWORD=/d' "$setup_dir/.env.prod.example"
        } > /srv/steimmo/shared/.env
    )
fi
chown deploy:"$(id -gn deploy)" /srv/steimmo/shared/.env
chmod 600 /srv/steimmo/shared/.env
nano /srv/steimmo/shared/.env
~~~

SMTP-Werte ausfüllen. Bei einer vorhandenen Env `STEIMMO_BIND_IP=172.17.0.1`
ergänzen. Den Proxy-Platzhalter erst nach der Messung unten ersetzen.
Bei einer bestehenden Datenbank deren bisheriges Passwort beibehalten.

~~~bash
steimmo_image=ghcr.io/steimmo/steimmo@sha256:c810727a7d5c270eac38065f8f15c63f094ca655e0cf9c8f789715ab394cd45f
runuser -u deploy -- docker pull "$steimmo_image"
~~~

Falls das Package privat ist, davor als `deploy` mit einem PAT classic
mit `read:packages` anmelden; Token nur am Passwortprompt eingeben:

~~~bash
runuser -u deploy -- docker login ghcr.io --username DEIN_GITHUB_BENUTZER
runuser -u deploy -- docker pull "$steimmo_image"
~~~

Nun die bestehende Proxy-Konfiguration sichern und bearbeiten:

~~~bash
cd /root/n8n-docker
cp -a docker-compose.yml "docker-compose.yml.backup-$(date +%Y%m%d-%H%M%S)"
cp -a Caddyfile "Caddyfile.backup-$(date +%Y%m%d-%H%M%S)"
nano docker-compose.yml
~~~

Unter den vorhandenen `volumes` des Dienstes `caddy` genau diese Zeile
ergänzen; alle übrigen Einträge beibehalten:

~~~yaml
- /srv/steimmo/public:/srv/steimmo/public:ro
~~~

Den Site-Block aus `ops/caddy-steimmo.caddy` direkt in die vorhandene
Datei kopieren. Eine bereits vorhandene Definition derselben Domain
ersetzen. Keine zusätzliche Importdatei anlegen: Im Container wird derzeit
ausschließlich das einzelne Caddyfile vom Host eingebunden.

~~~bash
cat "$setup_dir/caddy-steimmo.caddy"
nano /root/n8n-docker/Caddyfile
docker compose config --quiet
docker exec -i n8n-docker-caddy-1 caddy validate --config - --adapter caddyfile < Caddyfile
~~~

Nur nach erfolgreicher Validierung den Caddy-Dienst für den neuen Mount
einmalig neu erstellen. Dabei gibt es eine kurze Unterbrechung am gemeinsamen
Proxy. Daten-, Zertifikatsvolumes und andere Dienste bleiben bestehen.

~~~bash
docker compose up -d --no-deps --pull never --force-recreate caddy
docker exec n8n-docker-caddy-1 caddy validate --config /etc/caddy/Caddyfile
docker exec n8n-docker-caddy-1 caddy reload --config /etc/caddy/Caddyfile
proxy_ip=$(bash "$setup_dir/proxy-source.sh" n8n-docker-caddy-1 172.17.0.1 "$steimmo_image")
printf 'Gemessene Proxy-IP: %s\n' "$proxy_ip"
nano /srv/steimmo/shared/.env
chown deploy:"$(id -gn deploy)" /srv/steimmo/shared/.env
chmod 600 /srv/steimmo/shared/.env
~~~

Die gemessene IP in `DJANGO_LOGIN_THROTTLE_TRUSTED_PROXY_IPS` eintragen.
Alle Platzhalter ersetzen. Anschließend ausschließlich den Workflow vom
neuen `main` ausführen; ein erneuter Versuch des früheren Runs verwendet
weiterhin dessen alte Compose- und Deploy-Dateien.

`bash ops/smoke.sh <lokales-runtime-image>` prüft eine frische
Produktionsdatenbank, Produktionssettings, den nicht privilegierten Benutzer,
Static-Sammlung, Datenbank- und Media-Restore, HTTPS-Weiterleitung, Healthcheck
und die Persistenz nach Neuerstellung des Webcontainers. Ein echter
Caddy-Container läuft dazu in einem getrennten Docker-Netzwerk, verwendet
die Site-Konfiguration mit einer lokalen Test-CA und prüft HTTPS mit voller
Zertifikatsvalidierung. Zusätzlich werden Proxy-Quelladresse, Static-Wechsel
und Rollback bei unverändertem Read-only-Mount sowie private Dateipfade geprüft.
Auf Docker Desktop verwendet allein der lokale Test dessen Host-Verbindung
über `host.docker.internal` und Loopback; native Ubuntu-CI prüft die echte
Bridge-IP-Bindung. Alle dafür erzeugten
Ressourcen besitzen eigene Namen und werden nach dem Test entfernt. Dieser Test ist Teil der wiederverwendbaren
CI. `python -m unittest discover -s ops/tests -v` prüft zusätzlich Fehlerfälle
des echten Deploy-Skripts mit simulierten Docker- und HTTPS-Antworten.

### Vorausgehende Validierung am 2026-10-19

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

### Validierung der Docker-Caddy-Anpassung am 2026-10-19

- 726 Django-Tests sowie 15 Deploy-, SSH- und EntryPoint-Tests erfolgreich.
- Django-Systemcheck, Migrationsprüfung, Ruff und Formatprüfung erfolgreich.
- Echter Docker-Caddy in einem getrennten Bridge-Netzwerk: TLS mit geprüfter
  lokaler CA, Healthcheck, Startseite, App-/Admin-CSS, private Pfade,
  Read-only-Mount und Static-Wechsel samt Rollback ohne Caddy-Neustart erfolgreich.
- Datenbank-/Media-Restore und Persistenz nach Web-Neuerstellung erfolgreich.
- Die Betreiberangaben bestätigen Containername, Bridge-Netzwerk, IP und
  Konfigurationsmount. Das Netzwerk bzw. dessen aktuelle Container-IP wird
  nicht als Abhängigkeit in die STEImmo-Compose übernommen.
- Der vorausgehende Live-Workflow `39248132843`, Versuch 3, erreichte die
  SSH-Verbindung, endete aber ohne Release-Bestätigung mit Exit 1. Der neue
  SSH-Vorabcheck benennt ein fehlendes oder unzugängliches `shared` jetzt
  ausdrücklich. Die einmalige Servereinrichtung übernimmt der Betreiber.

Für den Betrieb gehören eine regelmäßige Sicherung von PostgreSQL und Media,
eine geschützte Kopie außerhalb dieses Servers sowie ein geprüfter Restore
zur Abnahme. Aufbewahrung und Zeitplan werden vor dem ersten produktiven
Datenbestand festgelegt. Ein persistentes Volume ersetzt kein Backup.

## Konsequenzen und verworfene Alternativen

Das Verfahren bleibt beim beschlossenen Monolithen und vorhandenen Stack.
Releases sind über Commit und Digest nachvollziehbar; der Server benötigt
keine Build-Werkzeuge. Das MVP akzeptiert ein kurzes Wartungsfenster bei
Releases; Blue/Green oder Kubernetes hätten dafür keinen belegten Nutzen.

Ein zweiter Caddy-Container würde die vorhandene Proxy-Infrastruktur
duplizieren. Eine zusätzliche Python-Static-Bibliothek entfällt, weil Caddy
die öffentlichen Assets bereits bedienen kann. Ein vollständiger
VORNIS-Compose-Stack würde unnötige Anwendungen und Abhängigkeiten einführen.
Ein Image-Rollback ohne Prüfung der Datenbankschema-Kompatibilität ist kein
verlässliches Wiederherstellungsverfahren.

Dieses ADR ist die zentrale Deployment-Dokumentation. Die README enthält
einen kurzen Verweis; ein paralleles Deployment-Konzept wird nicht geführt.
