# AGENTS.md

## Zweck

Diese Datei enthält verbindliche Regeln für Codex und andere Coding-Agents im Repository.

## Projektgrenzen

STEImmo ist ein einzelner Django-Monolith für die Immobilienverwaltung und -suche.

- Keine Microservices und keine separate Frontend-Anwendung
- Keine React-, Vue-, Bootstrap- oder Tailwind-Einführung
- Keine VORNIS-spezifischen Abhängigkeiten
- Keine neue Technologie ohne dokumentierten, konkreten MVP-Nutzen

## Verbindlicher Stack

- Python 3.13
- Django 5.2 LTS
- Serverseitige Django Templates
- UIkit als einziges UI-Framework
- UIkit JavaScript und bei Bedarf kleines Vanilla JavaScript
- PostgreSQL 17
- Docker Compose
- Gunicorn für den Produktionsbetrieb
- Django Test Framework
- Ruff für Formatierung und Linting

Django-Modelle, Views, Templates und Forms sind interne Schichten desselben Monolithen. Sie sind keine getrennten Services.

## UI-Regeln

- Nur freigegebene UIkit-Komponenten verwenden.
- Neue wiederverwendbare UI-Elemente als Django-Template-Partials anlegen.
- Eigenes CSS nur für Theme, Layout und begründete projektbezogene Anpassungen.
- Keine zweite UI-Bibliothek und keine individuelle Komponentenpalette pro Seite.
- Keine neue JavaScript-Abhängigkeit, wenn UIkit oder Vanilla JavaScript ausreicht.

## Arbeitsweise

1. Bestehende Struktur und betroffene Dateien zuerst prüfen.
2. Kleine, nachvollziehbare Änderungen vornehmen.
3. Fachliche oder technische Entscheidungen in einem ADR dokumentieren.
4. Keine Anforderungen eigenmächtig erweitern.
5. Keine Secrets, Zugangsdaten oder lokalen .env-Dateien committen.
6. Bei Datei-Uploads Authentifizierung, Berechtigungen, Dateityp und Dateigröße berücksichtigen.
7. Bestehende Datenbankmigrationen nicht nachträglich umschreiben; neue Migration erstellen.

## Qualität

Vor einem Commit, sofern die Projektstruktur die Befehle bereits bereitstellt:

- Django-Tests ausführen
- Ruff ausführen
- Django-Systemchecks ausführen
- Migrationen prüfen
- git diff --check ausführen

Wenn ein Test nicht ausgeführt werden kann, den Grund im Abschluss nennen.

## Sicherheits- und Änderungsgrenzen

Agents dürfen Code ändern und Tests ausführen. Löschen, Deployments, Änderungen an externen Systemen oder irreversible Datenänderungen benötigen eine ausdrückliche Freigabe.

Keine destruktiven Befehle ohne eindeutig abgegrenztes Ziel.

## Dokumentationsregeln

- README: Was ist das Projekt und wie wird es lokal gestartet?
- AGENTS.md: Wie sollen Agents in diesem Repository arbeiten?
- ADRs: Warum wurde eine relevante Entscheidung getroffen?
- Keine parallelen Dokumente mit demselben Inhalt.
