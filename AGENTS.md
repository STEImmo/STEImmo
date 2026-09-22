# AGENTS.md

## Zweck

Diese Datei enthält verbindliche Arbeitsregeln für Codex und andere Coding-Agents im STEImmo-Repository.

README.md richtet sich an Menschen. Diese Datei richtet sich an Agents und beschreibt deren Arbeitsweise, Grenzen und Qualitätsanforderungen.

Explizite Anweisungen des Nutzers haben Vorrang vor dieser Datei.

## Projektgrenzen

STEImmo ist ein einzelner Django-Monolith.

- genau eine Immobilie
- genau 25 Einheiten im MVP
- keine Funktion zur Verwaltung weiterer Immobilien
- Suche und Filter sind Pflicht
- Detailansichten sind Pflicht
- Anfragen und Bewerbungen sind Pflicht
- Dokumentenupload ist Pflicht
- Datepicker ist Pflicht
- Bewertungen sind außerhalb des MVP
- kein separates Frontend
- keine Microservices
- keine REST- oder GraphQL-API im MVP

Ein mögliches Property-Modell repräsentiert die eine Immobilie. Es darf nicht ohne neue Entscheidung zu einer Multi-Property-Verwaltung ausgebaut werden.

## Verbindlicher Stack

- Python 3.13
- Django 5.2 LTS
- Django Templates und serverseitiges HTML
- UIkit 3.25.24 als einziges UI-Framework
- UIkit JavaScript
- minimales Vanilla JavaScript nur bei echtem Bedarf
- PostgreSQL 18.6
- psycopg 3
- Docker Compose
- Gunicorn für Produktion
- Ruff
- Django Test Framework
- GitHub
- ein schlanker GitHub-Actions-CI-Workflow

Nicht ohne neue Entscheidung einführen:

- React
- Vue
- Bootstrap
- Tailwind
- HTMX
- Node.js-Buildchain
- pytest
- Playwright oder Selenium
- Cucumber
- Redis
- Celery
- Elasticsearch
- Kubernetes
- zusätzliche UI-Bibliotheken
- zusätzliche Architektur- oder Service-Schichten

Django-Modelle, Views, Formulare, Templates und ORM sind interne Schichten desselben Monolithen.

## UI-Regeln

UIkit ist die einzige Komponentenbasis.

Bevorzugte UIkit-Palette:

- Layout: Container, Grid, Flex, Section
- Navigation: Navbar, Breadcrumb, Pagination
- Inhalte: Card, Label, Badge, Alert
- Formulare: Form, Input, Select, Textarea, Button
- Interaktion: Modal, Dropdown, Offcanvas
- Dateien: Upload
- Datumsangaben: natives input[type="date"], kein Kalender-Framework

Regeln:

- bestehende UIkit-Komponenten wiederverwenden
- keine zweite Komponentenbibliothek einführen
- eigenes CSS nur für Theme, Layout und begründete Ausnahmen
- neue wiederverwendbare Elemente als Django-Template-Partials anlegen
- keine individuelle Komponentenpalette pro Seite
- keine neue JavaScript-Abhängigkeit, wenn UIkit oder Vanilla JavaScript ausreicht
- UIkit-Assets lokal versionieren; kein CDN als Laufzeitabhängigkeit
- UIkit bleibt auf Version 3.25.24; Updates benötigen eine dokumentierte Entscheidung.

## Entwicklungsprinzipien

### KISS

Die einfachste Lösung verwenden, die den MVP vollständig erfüllt.

Keine zusätzliche Schicht, Abstraktion oder Bibliothek ohne konkreten Nutzen.

### YAGNI

Keine Funktionen für spätere Multi-Property-Verwaltung, Bewertungen oder hypothetische Anforderungen bauen.

### Pragmatic DRY

Duplikation erst abstrahieren, wenn sie tatsächlich mehrfach auftritt und die Abstraktion verständlich bleibt.

Keine generischen Frameworks oder Basisabstraktionen im Voraus entwickeln.

### Vertical Slices

Funktionen möglichst vollständig umsetzen:

Modell → Formular → View → Template → Test → Dokumentation

Keine großen, voneinander getrennten Backend-, Frontend- und Testphasen ohne lauffähigen Zwischenstand.

### TDD

Für fachliches Verhalten gilt:

1. Test für das erwartete Verhalten schreiben
2. Test fehlschlagen lassen
3. minimalen Code zur Erfüllung schreiben
4. Tests ausführen
5. Code refactoren

TDD gilt insbesondere für:

- Such- und Filterlogik
- Formulare und Validierung
- Rollen und Berechtigungen
- Statuswechsel
- Dokumentenuploads
- Anfragen und Bewerbungen

Für reine Template-Struktur oder CSS ist kein künstlicher Test erforderlich. Dort erfolgen Django-Response-Tests und ein manueller Browser-Smoke-Test.

## Verbindlicher Arbeitszyklus

~~~mermaid
flowchart TD
    I["Issue prüfen"] --> A["Akzeptanzkriterien klären"]
    A --> T["Test zuerst"]
    T --> C["Implementieren"]
    C --> Q["Qualitätschecks"]
    Q --> D["Dokumentation aktualisieren"]
    D --> R["Review und Issue abschließen"]
~~~

Vor jeder Änderung:

1. Repository-Struktur und betroffene Dateien prüfen
2. zugehöriges GitHub-Issue suchen
3. bestehende Implementierung und Dokumentation lesen
4. Anforderungen und Akzeptanzkriterien prüfen
5. bei wesentlichen Unklarheiten nachfragen
6. bei größeren Änderungen einen kurzen Plan erstellen

## Tests und Qualitätsgates

Vor Abschluss einer Änderung, sofern die Projektstruktur dies ermöglicht:

- Django-Tests ausführen
- python manage.py check
- python manage.py makemigrations --check --dry-run
- ruff check .
- ruff format --check .
- git diff --check

Zusätzlich prüfen:

- Berechtigungen und Zugriffsschutz
- CSRF-Schutz bei Formularen
- Upload-Dateityp und Dateigröße
- korrekte Fehlerbehandlung
- keine Secrets oder echten Nutzerdokumente im Repository

Fehlgeschlagene oder nicht ausführbare Prüfungen müssen im Abschlussbericht genannt werden.

## GitHub-Issue-Prozess

GitHub Issues sind die verbindliche Arbeitsgrundlage für technische Aufgaben.

### Vor der Umsetzung

- bestehende Issues durchsuchen
- keine Duplikate anlegen
- Ziel und Akzeptanzkriterien prüfen
- Out-of-Scope und Abhängigkeiten festhalten
- Unteraufgaben als Checkliste im Issue führen

Minimaler Issue-Aufbau:

~~~markdown
## Ziel

## Akzeptanzkriterien

- [ ] ...

## Nicht Bestandteil

## Abhängigkeiten

## Technische Hinweise
~~~

### Während der Umsetzung

Das zuständige Issue wird aktualisiert, wenn:

- eine technische Entscheidung getroffen wurde
- sich der Umfang ändert
- ein Blocker entsteht
- eine Abhängigkeit bekannt wird
- Tests oder Checks fehlschlagen
- Dokumentation angepasst werden muss

Kleine Erweiterungen können im bestehenden Issue ergänzt werden. Eine neue fachliche Funktion erhält ein eigenes verknüpftes Issue.

### Abschluss

Ein Issue darf erst geschlossen werden, wenn:

- alle Akzeptanzkriterien erfüllt sind
- Tests und Qualitätschecks erfolgreich waren
- notwendige Dokumentation aktualisiert wurde
- keine offenen Blocker bestehen
- der Abschluss im Issue dokumentiert wurde

Der Abschlusskommentar enthält mindestens:

- Ergebnis
- geänderte Bereiche
- ausgeführte Tests
- offene Risiken oder Nacharbeiten

### Aufräumen

- Duplikate kommentieren, auf das führende Issue verweisen und schließen
- veraltete Issues nicht löschen, sondern begründen und schließen oder als blockiert markieren
- erledigte Issues schließen
- keine Issue-Historie ohne nachvollziehbaren Grund entfernen
- Projektmanagement-Issues nicht eigenständig bearbeiten
- keine massenhaften Issue-Änderungen ohne ausdrücklichen Auftrag

Agents dürfen das Issue der ausdrücklich beauftragten technischen Aufgabe aktualisieren und nach erfüllter Definition of Done schließen. Fremde oder organisatorische Issues bleiben unangetastet.

## Dokumentationsregeln

| Änderung | Dokumentation |
|---|---|
| MVP- oder Roadmap-Änderung | README.md |
| Agentenregel | AGENTS.md |
| Architekturentscheidung | ADR unter docs/decisions/ |
| Arbeitsfortschritt | GitHub-Issue |
| Bugfix | Issue und gegebenenfalls README/ADR prüfen |

Keine doppelte oder widersprüchliche Dokumentation erzeugen.

## Sicherheits- und Änderungsgrenzen

Agents dürfen nach einem eindeutigen Auftrag Code, Tests und zugehörige Dokumentation ändern.

Ohne ausdrückliche Freigabe nicht ausführen:

- git push
- Pull Request mergen
- Deployment
- Löschen größerer Datenmengen
- Änderungen an externen Systemen
- irreversible Datenbankänderungen

Lokale, reversible Prüfungen sind erlaubt.

## Definition of Done

Eine Aufgabe ist abgeschlossen, wenn:

- das zugehörige Issue erfüllt ist
- die Akzeptanzkriterien erfüllt sind
- Tests und Qualitätschecks erfolgreich sind
- Migrationen korrekt enthalten sind
- relevante Dokumentation aktuell ist
- keine Secrets oder Testdaten versehentlich versioniert wurden
- das Issue aktualisiert und geschlossen wurde

## Abschlussbericht

~~~text
Ergebnis:
Geänderte Dateien:
Tests und Checks:
Dokumentation:
Aktualisiertes Issue:
Offene Punkte:
~~~
