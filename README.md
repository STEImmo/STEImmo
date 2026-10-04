# STEImmo

STE Immobilien eGbR

## Projektziel

STEImmo ist eine serverseitig gerenderte Webanwendung für die Verwaltung und Vermarktung einer Immobilie mit 25 Wohneinheiten.

Studierende können verfügbare Einheiten suchen, filtern, ansehen und sich darauf bewerben. Die Immobiliengesellschaft verwaltet die Einheiten sowie eingehende Anfragen und Bewerbungen.

## Projektstatus

Der Stack ist festgelegt. Die Foundation ist umgesetzt; die fachlichen MVP-Vertical-Slices folgen.

Statussymbole:

- ✅ entschieden oder abgeschlossen
- 🔄 in Arbeit
- ⬜ geplant
- 🚫 außerhalb des MVP

## MVP-Umfang

### Im MVP enthalten

- eine Immobilie mit 25 Einheiten
- Verwaltung der Immobilie und ihrer Einheiten
- Suche und Filter
- Detailansichten
- Anfragen von Studierenden
- Bewerbungen
- Dokumentenupload
- Datepicker für Datumsangaben
- Rollen und Berechtigungen
- lokales Entwickeln mit Docker
- Deployment auf dem Uni-Server

### Nicht im MVP enthalten

- Verwaltung weiterer Immobilien
- Bewertungssystem
- separate Frontend-Anwendung
- REST- oder GraphQL-API
- Echtzeitfunktionen
- Microservices
- individuelle UI-Komponentenbibliotheken

Bewertungen und die Verwaltung weiterer Immobilien gehören in eine spätere Roadmap.

## Technischer Stack

| Bereich | Entscheidung |
|---|---|
| Sprache | Python 3.13 |
| Backend | Django 5.2 LTS |
| Architektur | Ein Django-Monolith |
| Rendering | Serverseitige Django Templates und HTML |
| UI | UIkit 3.25.24 mit verbindlicher Komponentenpalette |
| JavaScript | UIkit JavaScript und minimales Vanilla JavaScript |
| Datenbank | PostgreSQL 18.6 |
| Datenbanktreiber | psycopg 3 |
| Dateien | Django Media-Storage mit persistentem Volume |
| Lokale Entwicklung | Docker Compose |
| Produktion | Gunicorn hinter dem Uni-Reverse-Proxy |
| Qualität | Ruff und Django Test Framework |
| Versionsverwaltung | GitHub |
| CI | Schlanker GitHub-Actions-Workflow |

## Architektur

Alle Bestandteile laufen in einem einzigen Django-Monolithen. Django-Modelle, Views, Formulare und Templates sind interne Schichten derselben Anwendung und keine separaten Services.

~~~mermaid
flowchart TD
    U["Studierende / Immobiliengesellschaft"] --> B["Browser"]
    B --> D["Django-Monolith<br/>Templates + UIkit"]
    D --> P["PostgreSQL"]
    D --> M["Media-Volume"]
~~~

## Technische Roadmap

| Phase | Technische Lieferobjekte | Fertigkriterium | Status |
|---|---|---|---|
| 1. Foundation | Django-Projekt, Docker Compose, PostgreSQL, Umgebungsvariablen, Ruff, CI-Grundlage | Container startet, Datenbankverbindung und Basischecks funktionieren | ✅ |
| 2. Webapp-Basis | Settings, URL-Struktur, Static/Media, Base-Templates, lokale UIkit-Assets | Eine Basis-Seite läuft mit einheitlichem UI | ✅ |
| 3. Domänenmodell | Eine Immobilie, 25 Einheiten, Anfragen, Bewerbungen und Dokumente als Django-Modelle inklusive Migrationen | Modelle, Migrationen und Testdaten funktionieren | ⬜ |
| 4. Authentifizierung | Django-User, Gruppen, Rollen und Berechtigungen für Studierende und Immobiliengesellschaft | Zugriffsschutz ist umgesetzt und getestet | 🔄 |
| 5. Verwaltungsbereich | Verwaltungsansichten und Formulare für Einheiten, Anfragen, Bewerbungen und Dokumente | Gesellschaft kann den Bestand und Vorgänge verwalten | ⬜ |
| 6. Studentenbereich | ORM-Suche, Filter, Pagination und Detailansichten | Studierende können Einheiten zuverlässig finden und ansehen | ⬜ |
| 7. Anfrage und Bewerbung | Formulare, Statusverwaltung, Datepicker, Upload-Validierung und Dateispeicherung | Kernabläufe inklusive Fehlerfällen sind getestet | ⬜ |
| 8. Qualität und Betrieb | Tests, Django-Checks, Ruff, Produktionssettings, Gunicorn, Static/Media und Deployment | CI ist erfolgreich und Deployment auf dem Uni-Server funktioniert | ⬜ |

Eine Roadmap-Phase gilt erst als abgeschlossen, wenn ihre Akzeptanzkriterien erfüllt, getestet und im zugehörigen GitHub-Issue dokumentiert sind.

## Benutzerkonten und Zugriff

Öffentliche Seiten sind ohne Konto erreichbar. Angemeldete Konten erhalten Zugriffe über feste Gruppen; zusätzliche Seitenrechte können in der Benutzerverwaltung gezielt pro Konto vergeben werden.

| Gruppe | Zugriff |
|---|---|
| `Bewerber` | Eigene Bewerbungen erstellen, Bearbeitungsstände einsehen und freigeschaltete Bewerbungen zurückziehen |
| `Mieter` | Eigene bestätigte Übergabeprotokolle ansehen und als PDF herunterladen |
| `Mitarbeiter` | Verwaltungsbereich und Übergabeprotokolle |
| `Benutzerverwaltung` | Mitarbeiterzugriff sowie Konten, Rollen und Seitenrechte verwalten |

Konten mit Mitarbeiterzugriff oder Benutzerverwaltung – auch bei direkt zugewiesenem Einzelrecht – benötigen bei jeder Anmeldung zusätzlich zum Passwort einen sechsstelligen E-Mail-Einmalcode. Der Code ist 15 Minuten gültig, wird nur gehasht gespeichert und erlaubt höchstens fünf Versuche. Es gibt bewusst keine dauerhafte Browserfreigabe. In der lokalen Entwicklungsumgebung erscheint der Code im automatisch gestarteten Mailpit-Postfach unter [http://localhost:8025](http://localhost:8025); Produktion verwendet den konfigurierten SMTP-Backend.

Die reguläre Anmeldung unter `/accounts/login/` sperrt nach drei falschen Passwörtern das betroffene Konto für 15 Minuten. Zusätzlich werden zehn fehlgeschlagene Anmeldungen derselben IP-Adresse innerhalb von 15 Minuten begrenzt. Die Anwendung speichert dafür nie die IP-Adresse selbst, sondern nur einen mit dem Servergeheimnis abgeleiteten Fingerprint. Falsches Passwort, unbekanntes Konto und Sperren liefern dieselbe neutrale Meldung. Django-Admin ist bewusst nicht Teil dieser Anmeldestrecke. Hinter einem Reverse-Proxy darf `DJANGO_LOGIN_THROTTLE_TRUSTED_PROXY_IPS` ausschließlich mit dessen vertrauenswürdigen IP-Adressen gesetzt werden; nur dann wird dessen `X-Forwarded-For` berücksichtigt.

Nach dem Ausführen der Migrationen wird der erste Benutzerverwalter einmalig angelegt:

~~~bash
docker compose exec web python manage.py create_initial_user_manager \
  --email verwaltung@example.test \
  --password 'ein-sicheres-passwort' \
  --first-name Verwaltung \
  --last-name Beispiel
~~~

Danach werden Konten im UIkit-Bereich **Verwaltung → Benutzer** erstellt, mit einer bestehenden konto-losen Person verknüpft oder zusammen mit einer neuen Person erfasst. Konten werden deaktiviert statt gelöscht. Die technische Rechte-Matrix und die Regel zum Ergänzen weiterer geschützter Seiten stehen in [ADR-0008](docs/decisions/0008-rollen-und-zugriffskontrolle.md).

Selbstregistrierte Bewerberkonten bleiben bis zur Eingabe eines per E-Mail gesendeten, sechsstelligen Bestätigungscodes deaktiviert. Der Code ist 15 Minuten gültig; nach fünf falschen Versuchen ist ein neuer Code anzufordern. Die lokale Entwicklungsumgebung startet dafür automatisch Mailpit. Das lokale Testpostfach ist unter [http://localhost:8025](http://localhost:8025) erreichbar und bewahrt höchstens 100 E-Mails bis zum Stoppen des Containers auf. Es werden keine E-Mails an externe Empfänger gesendet.

Mit dem Development-Override wird beim Containerstart außerdem ein ausschließlich lokales Mitarbeiterkonto bereitgestellt. Es existiert nicht in der Produktions-Compose-Konfiguration und der zugrunde liegende Command verweigert die Ausführung bei `DEBUG=False`.

| E-Mail-Adresse | Passwort | Zugriff |
|---|---|---|
| `mitarbeiter@example.test` | `KometFjord!4826` | Mitarbeiterbereich und Übergaben |

Der lokale Bootstrap reaktiviert dieses fiktive Konto und setzt sein Passwort bei jedem Entwicklungsstart auf den dokumentierten Wert zurück. Die Zugangsdaten sind absichtlich öffentlich und dürfen niemals außerhalb der lokalen Entwicklungsumgebung verwendet werden.

Für den Produktivbetrieb wird der SMTP-Backend über Umgebungsvariablen konfiguriert: `DJANGO_EMAIL_BACKEND`, `DJANGO_DEFAULT_FROM_EMAIL`, `DJANGO_EMAIL_HOST`, `DJANGO_EMAIL_PORT`, `DJANGO_EMAIL_HOST_USER`, `DJANGO_EMAIL_HOST_PASSWORD` und `DJANGO_EMAIL_USE_TLS`. Zugangsdaten gehören ausschließlich in die nicht versionierte Serverkonfiguration.

## Lokale Entwicklung

Übergabeprotokolle werden über **Protokoll prüfen und unterschreiben** abgeschlossen.
Mitarbeiter und Mieter unterschreiben mit Finger, Stift oder Maus auf demselben
Gerät. Fehlt die Mieterunterschrift, muss der Mitarbeiter dies begründen.
Nach erfolgreichem Abschluss steht die dauerhaft gespeicherte PDF-Fassung bereit;
Mieter finden ihre Downloads unter **Meine Übergabeprotokolle**. Für Altprotokolle
gibt es einen ausdrücklich gekennzeichneten nachträglichen Export.
Die Entscheidungen und Speicherregeln stehen in
[ADR-0014](docs/decisions/0014-pdf-export-und-touch-unterschriften.md).

Die lokale Entwicklungsumgebung läuft vollständig über Docker. Python und PostgreSQL müssen daher nicht separat auf dem Entwicklungsrechner installiert werden.

### Voraussetzungen

- Git
- Docker mit Docker Compose
  - Windows: Docker Desktop
  - macOS (Intel oder Apple Silicon): Docker Desktop
  - Linux: Docker Engine mit Compose-Plugin
- optional: IntelliJ IDEA / PyCharm oder eine andere IDE

Nach der Installation prüfen:

~~~bash
docker --version
docker compose version
~~~

Alle folgenden Befehle werden im Root-Verzeichnis des geklonten Repositories ausgeführt. In IntelliJ oder PyCharm kann dafür direkt das integrierte Terminal verwendet werden.

### 1. Lokale Umgebungsdatei anlegen

macOS / Linux sowie Git Bash unter Windows:

~~~bash
cp docker/.env.example docker/.env
~~~

Windows PowerShell:

~~~powershell
Copy-Item docker/.env.example docker/.env
~~~

Die Datei `docker/.env` ist nur für die lokale Entwicklung vorgesehen und wird nicht versioniert.

### 2. Entwicklungsumgebung starten

Der folgende Befehl ist unter macOS, Linux und Windows PowerShell identisch:

~~~bash
docker compose --env-file docker/.env -f docker/compose.yaml -f docker/compose.dev.yaml up --build
~~~

Beim ersten Start werden die benötigten Docker-Images geladen und das Anwendungs-Image gebaut. Sobald die Container laufen, ist die Anwendung unter [http://localhost:8000](http://localhost:8000) erreichbar.

Beim Start wartet der Web-Container auf den gesunden PostgreSQL-Dienst und führt anschließend mit `python manage.py migrate --noinput` alle ausstehenden Django-Migrationen aus. Die Datenbankstruktur wird dadurch beim ersten Start angelegt und bei späteren Versionen schrittweise erweitert. Das PostgreSQL-Volume muss für normale Strukturänderungen nicht gelöscht werden.

Neue Strukturänderungen werden ausschließlich über Django-Modelle und versionierte Migrationen eingebracht:

~~~bash
docker compose --env-file docker/.env -f docker/compose.yaml -f docker/compose.dev.yaml exec web python manage.py makemigrations
docker compose --env-file docker/.env -f docker/compose.yaml -f docker/compose.dev.yaml exec web python manage.py migrate
~~~

Der Befehl läuft standardmäßig im Vordergrund. Für einen Start im Hintergrund kann `-d` ergänzt werden:

~~~bash
docker compose --env-file docker/.env -f docker/compose.yaml -f docker/compose.dev.yaml up --build -d
~~~

### 3. Projekt prüfen

Bei laufenden Containern können die Prüfungen aus einem zweiten Terminal ausgeführt werden:

~~~bash
docker compose --env-file docker/.env -f docker/compose.yaml -f docker/compose.dev.yaml exec web python manage.py check
docker compose --env-file docker/.env -f docker/compose.yaml -f docker/compose.dev.yaml exec web python manage.py test
docker compose --env-file docker/.env -f docker/compose.yaml -f docker/compose.dev.yaml exec web ruff check .
docker compose --env-file docker/.env -f docker/compose.yaml -f docker/compose.dev.yaml exec web ruff format --check .
~~~

Für eine erfolgreiche Foundation-Prüfung müssen alle vier Befehle ohne Fehler durchlaufen.

### 4. Entwicklungsumgebung beenden

~~~bash
docker compose --env-file docker/.env -f docker/compose.yaml -f docker/compose.dev.yaml down
~~~

Die persistenten Docker-Volumes für PostgreSQL und hochgeladene Dateien bleiben dabei erhalten.

`compose.dev.yaml` aktiviert den Django-Entwicklungsserver und bindet den lokalen Quellcode in den Container ein. Änderungen am Python-, Template- oder Static-Code sind dadurch direkt aus IntelliJ/PyCharm möglich. Ohne den Development-Override startet `compose.yaml` die Anwendung mit Gunicorn und ist für den späteren Serverbetrieb vorgesehen.

## Foundation-Struktur

~~~text
config/                 Django-Projektkonfiguration
core/                   technische Basisansichten und Healthcheck
wohnungsverwaltung/     fachliches Datenmodell und PostgreSQL-Migrationen
templates/              serverseitige Django-Templates
static/                 lokale UIkit-Assets und Projekt-Styles
docker/                 Compose, Umgebungsvariablen und EntryPoint
.github/workflows/      schlanke CI-Prüfungen
~~~

## GitHub und Dokumentation

- GitHub Issues enthalten technische Aufgaben, Akzeptanzkriterien und Fortschritt.
- Die README zeigt den Projekt- und Roadmap-Status.
- AGENTS.md enthält verbindliche Regeln für Coding-Agents.
- Architekturentscheidungen werden unter docs/decisions/ dokumentiert.
- [ADR-0002](docs/decisions/0002-django-migrationen.md) beschreibt Django-Migrationen als Quelle der Datenbankstruktur.
- Einzelne Issue-Inhalte werden nicht vollständig in der README dupliziert.

## Portierbarkeit

Die Anwendung bleibt durch Docker Compose, PostgreSQL, Umgebungsvariablen und persistente Volumes auf andere Server portierbar. 
