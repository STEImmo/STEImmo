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
| 1. Foundation | Django-Projekt, Docker Compose, PostgreSQL, Umgebungsvariablen, Ruff, CI-Grundlage | Container startet, Datenbankverbindung und Basischecks funktionieren | ⬜ |
| 2. Webapp-Basis | Settings, URL-Struktur, Static/Media, Base-Templates, lokale UIkit-Assets | Eine Basis-Seite läuft mit einheitlichem UI | ✅ |
| 3. Domänenmodell | Eine Immobilie, 25 Einheiten, Anfragen, Bewerbungen und Dokumente als Django-Modelle inklusive Migrationen | Modelle, Migrationen und Testdaten funktionieren | ⬜ |
| 4. Authentifizierung | Django-User, Gruppen, Rollen und Berechtigungen für Studierende und Immobiliengesellschaft | Zugriffsschutz ist umgesetzt und getestet | ⬜ |
| 5. Verwaltungsbereich | Verwaltungsansichten und Formulare für Einheiten, Anfragen, Bewerbungen und Dokumente | Gesellschaft kann den Bestand und Vorgänge verwalten | ⬜ |
| 6. Studentenbereich | ORM-Suche, Filter, Pagination und Detailansichten | Studierende können Einheiten zuverlässig finden und ansehen | ⬜ |
| 7. Anfrage und Bewerbung | Formulare, Statusverwaltung, Datepicker, Upload-Validierung und Dateispeicherung | Kernabläufe inklusive Fehlerfällen sind getestet | ⬜ |
| 8. Qualität und Betrieb | Tests, Django-Checks, Ruff, Produktionssettings, Gunicorn, Static/Media und Deployment | CI ist erfolgreich und Deployment auf dem Uni-Server funktioniert | ⬜ |

Eine Roadmap-Phase gilt erst als abgeschlossen, wenn ihre Akzeptanzkriterien erfüllt, getestet und im zugehörigen GitHub-Issue dokumentiert sind.

## Lokale Entwicklung

Voraussetzung sind Docker Engine und Docker Compose.

~~~bash
cp docker/.env.example docker/.env
docker compose --env-file docker/.env -f docker/compose.yaml -f docker/compose.dev.yaml up --build
~~~

Die Anwendung ist anschließend unter [http://localhost:8000](http://localhost:8000) erreichbar.

Prüfungen innerhalb des laufenden Web-Containers:

~~~bash
docker compose --env-file docker/.env -f docker/compose.yaml -f docker/compose.dev.yaml exec web python manage.py check
docker compose --env-file docker/.env -f docker/compose.yaml -f docker/compose.dev.yaml exec web python manage.py test
docker compose --env-file docker/.env -f docker/compose.yaml -f docker/compose.dev.yaml exec web ruff check .
docker compose --env-file docker/.env -f docker/compose.yaml -f docker/compose.dev.yaml exec web ruff format --check .
~~~

Beenden:

~~~bash
docker compose --env-file docker/.env -f docker/compose.yaml -f docker/compose.dev.yaml down
~~~

`compose.dev.yaml` aktiviert den Entwicklungsserver mit Quellcode-Mount. Ohne den Override startet `compose.yaml` mit Gunicorn und ist für den späteren Serverbetrieb vorgesehen.

## Foundation-Struktur

~~~text
config/                 Django-Projektkonfiguration
core/                   technische Basisansichten und Healthcheck
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
- Einzelne Issue-Inhalte werden nicht vollständig in der README dupliziert.

## Portierbarkeit

Die Anwendung bleibt durch Docker Compose, PostgreSQL, Umgebungsvariablen und persistente Volumes auf andere Server portierbar. 
