# STEImmo

STE Immobilien eGbR

## Projektziel

STEImmo ist eine serverseitig gerenderte Webanwendung für die Verwaltung und Vermarktung einer Immobilie mit 25 Wohneinheiten.

Studierende können verfügbare Einheiten suchen, filtern, ansehen und sich darauf bewerben. Die Immobiliengesellschaft verwaltet die Einheiten sowie eingehende Anfragen und Bewerbungen.

## Projektstatus

Der technische Stack und die Entwicklungsregeln sind festgelegt. Die Implementierung des MVP befindet sich noch in der Vorbereitung.

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
| UI | UIkit 3 mit verbindlicher Komponentenpalette |
| JavaScript | UIkit JavaScript und minimales Vanilla JavaScript |
| Datenbank | PostgreSQL 17 |
| Datenbanktreiber | psycopg 3 |
| Dateien | Django Media-Storage mit persistentem Volume |
| Lokale Entwicklung | Docker Compose |
| Produktion | Gunicorn hinter dem Uni-Reverse-Proxy |
| Qualität | Ruff und Django Test Framework |
| Versionsverwaltung | GitHub |
| CI | Geplant: ein schlanker GitHub-Actions-Workflow |

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
| 2. Webapp-Basis | Settings, URL-Struktur, Static/Media, Base-Templates, lokale UIkit-Assets | Eine Basis-Seite läuft mit einheitlichem UI | ⬜ |
| 3. Domänenmodell | Eine Immobilie, 25 Einheiten, Anfragen, Bewerbungen und Dokumente als Django-Modelle inklusive Migrationen | Modelle, Migrationen und Testdaten funktionieren | ⬜ |
| 4. Authentifizierung | Django-User, Gruppen, Rollen und Berechtigungen für Studierende und Immobiliengesellschaft | Zugriffsschutz ist umgesetzt und getestet | ⬜ |
| 5. Verwaltungsbereich | Verwaltungsansichten und Formulare für Einheiten, Anfragen, Bewerbungen und Dokumente | Gesellschaft kann den Bestand und Vorgänge verwalten | ⬜ |
| 6. Studentenbereich | ORM-Suche, Filter, Pagination und Detailansichten | Studierende können Einheiten zuverlässig finden und ansehen | ⬜ |
| 7. Anfrage und Bewerbung | Formulare, Statusverwaltung, Datepicker, Upload-Validierung und Dateispeicherung | Kernabläufe inklusive Fehlerfällen sind getestet | ⬜ |
| 8. Qualität und Betrieb | Tests, Django-Checks, Ruff, Produktionssettings, Gunicorn, Static/Media und Deployment | CI ist erfolgreich und Deployment auf dem Uni-Server funktioniert | ⬜ |

Eine Roadmap-Phase gilt erst als abgeschlossen, wenn ihre Akzeptanzkriterien erfüllt, getestet und im zugehörigen GitHub-Issue dokumentiert sind.

## Lokale Entwicklung

Die verbindlichen Start- und Testbefehle werden ergänzt, sobald die Docker- und Django-Grundlage im Repository vorhanden ist. Es werden nur geprüfte Befehle dokumentiert.

## GitHub und Dokumentation

- GitHub Issues enthalten technische Aufgaben, Akzeptanzkriterien und Fortschritt.
- Die README zeigt den Projekt- und Roadmap-Status.
- AGENTS.md enthält verbindliche Regeln für Coding-Agents.
- Architekturentscheidungen werden unter docs/decisions/ dokumentiert.
- Einzelne Issue-Inhalte werden nicht vollständig in der README dupliziert.

## Portierbarkeit

Die Anwendung bleibt durch Docker Compose, PostgreSQL, Umgebungsvariablen und persistente Volumes auf andere Server portierbar. 
