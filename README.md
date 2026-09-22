# STEImmo

STE Immobilien eGbR

## Projekt

STEImmo ist eine kleine Webanwendung für die Immobilienverwaltung und -suche.

- Immobiliengesellschaft: Immobilien anlegen, verwalten und veröffentlichen
- Studierende: Immobilien suchen, filtern, ansehen und Anfragen stellen
- Erweiterungen im MVP-Umfeld: Bewertungen, Termine/Kalender und Dokumentenupload

Das System bleibt ein einzelner Monolith. Es gibt keine separate Frontend-Anwendung und keine Microservices.

## Finaler Stack

| Bereich | Entscheidung |
|---|---|
| Sprache | Python 3.13 |
| Backend | Django 5.2 LTS |
| Architektur | Django-Monolith |
| Frontend | Serverseitige Django Templates |
| UI | UIkit mit verbindlicher Komponenten-Whitelist |
| Browser-Interaktionen | UIkit JavaScript, ergänzend kleines Vanilla JavaScript |
| Datenbank | PostgreSQL 17 |
| Deployment | Docker Compose lokal und auf dem Uni-Server |
| Produktionsserver | Gunicorn im Django-Container |
| Tests | Django Test Framework |
| Codequalität | Ruff als Entwicklungswerkzeug |
| Versionsverwaltung | GitHub |

### UI-Regel

UIkit ist das einzige UI-Framework. React, Vue, Bootstrap, Tailwind und weitere UI-Komponentenbibliotheken werden nicht eingeführt.

Eigene Styles sind auf ein gemeinsames Theme, Layout-Anpassungen und projektbezogene Ausnahmen zu beschränken. Neue Komponenten werden als wiederverwendbare Django-Template-Partials umgesetzt.

### MAO-Regel

Jede zusätzliche Abhängigkeit muss einen konkreten Nutzen für den MVP nachweisen. Keine Technologie wird nur für mögliche spätere Anforderungen eingeführt.

## Betrieb

Docker Compose stellt lokal und auf dem Uni-Server dieselbe technische Grundlage bereit:

- Django-Anwendung
- PostgreSQL
- persistente Volumes für Daten und hochgeladene Dateien

Konfiguration und Geheimnisse werden über Umgebungsvariablen eingebunden und nicht in Git versioniert.

Ein Reverse Proxy bzw. TLS wird nur ergänzt, wenn der konkrete Server dies benötigt. Kubernetes, eine separate Container-Orchestrierung oder eine Cloud-Abhängigkeit sind nicht vorgesehen.

## Portierbarkeit zu VORNIS

Die Anwendung bleibt durch Docker, PostgreSQL, Umgebungsvariablen und persistente Volumes portierbar. VORNIS-spezifische Abhängigkeiten werden nicht in den Uni-MVP eingebaut.

## Dokumentation

- [AGENTS.md](AGENTS.md): verbindliche Arbeitsregeln für Codex und andere Coding-Agents
- [ADR-0001](docs/decisions/0001-stack.md): Begründung des finalen Stacks
- Diese README: Projekt, Startpunkt und technische Übersicht

## Status

Der Stack ist entschieden. Als Nächstes werden Projektstruktur, Docker-Konfiguration und die fachlichen MVP-Anforderungen umgesetzt.
