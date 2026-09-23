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

## Repository- und Git-Konventionen

### Branches

Branches werden grundsätzlich vom aktuellen `main` erstellt.

Standardformat:

~~~text
<type>/<issue>-<kurzbeschreibung>
~~~

Beispiele:

~~~text
feat/42-unit-search
fix/51-upload-validation
refactor/63-application-status
test/70-filter-tests
docs/71-readme-setup
chore/72-ci-cleanup
~~~

Erlaubte Branch-Typen:

- `feat`: neue fachliche Funktion
- `fix`: Fehlerbehebung
- `refactor`: interne Umstrukturierung ohne fachliche Änderung
- `test`: reine Teständerung
- `docs`: reine Dokumentationsänderung
- `chore`: Build-, CI-, Tooling- oder Repository-Pflege

Regeln:

- Branch-Namen verwenden ausschließlich Kleinbuchstaben, Ziffern, Bindestriche und den Trenner `/`.
- Kurzbeschreibungen stehen in `kebab-case`.
- keine Personennamen, Initialen oder Entwicklerkürzel im Branch-Namen
- ein Branch gehört grundsätzlich zu genau einem Issue
- mehrere unabhängige Issues nicht in einem Branch bündeln
- Branch vor Beginn auf aktuellen `main`-Stand bringen
- nach Merge den Branch löschen
- keine langfristigen Sammelbranches wie `develop`, `dev` oder `feature-all`

Für kleine, ausdrücklich beauftragte Repository- oder Dokumentationsänderungen ohne eigenes Issue ist ausnahmsweise `<type>/<kurzbeschreibung>` zulässig.

### main

`main` ist der Integrationsbranch und soll jederzeit in einem lauffähigen Zustand bleiben.

Regeln:

- normale Entwicklung nie direkt auf `main`
- Änderungen über Branch und Pull Request
- kein Force-Push auf `main`
- keine unfertigen oder experimentellen Änderungen auf `main`
- direkte Änderungen auf `main` nur nach ausdrücklicher Anweisung für einen klar begrenzten administrativen Sonderfall
- vor jeder Änderung aktuellen `main`-Stand prüfen

### Commits

Commit-Nachrichten verwenden:

~~~text
<type>: <imperative description>
~~~

Beispiele:

~~~text
feat: add unit availability filter
fix: validate uploaded file size
refactor: simplify application status handling
test: cover invalid inquiry submission
docs: document local setup
chore: minimize CI triggers
~~~

Regeln:

- Commit-Typ entspricht möglichst dem Branch-Typ.
- Beschreibung kurz, konkret und auf Englisch.
- Imperative Form bevorzugen.
- ein Commit enthält eine logisch zusammengehörige Änderung
- keine finalen Commit-Nachrichten wie `wip`, `update`, `changes`, `stuff`, `fix` oder `test123`
- keine generierten Artefakte oder unbeabsichtigten Formatierungsänderungen mit fachlichen Änderungen vermischen
- Secrets, echte Nutzerdaten und lokale Konfigurationen dürfen nie Bestandteil eines Commits sein

### Pull Requests

Pull Requests sind klein und auf ein Issue beziehungsweise eine klar abgegrenzte Aufgabe beschränkt.

PR-Titel verwenden ebenfalls das Schema:

~~~text
<type>: <kurze Beschreibung>
~~~

Eine PR-Beschreibung enthält mindestens:

~~~markdown
## Ziel

## Issue

Closes #123

## Änderungen

## Tests und Checks

## Offene Punkte
~~~

Regeln:

- `Closes #<issue>` nur verwenden, wenn der PR das Issue vollständig erfüllt
- bei Teilumsetzungen stattdessen `Refs #<issue>`
- keine fachlich unabhängigen Änderungen in denselben PR aufnehmen
- keine reine Aufräum- oder Refactoring-Arbeit in einem fachlichen PR verstecken
- vor Review den eigenen Diff vollständig prüfen
- offene bekannte Risiken im PR dokumentieren

### Ready for Review

Ein PR darf erst als Ready for Review markiert werden, wenn:

- das zugehörige Issue eindeutig referenziert ist
- der Scope des Issues eingehalten wurde
- die Implementierung fachlich vollständig ist
- notwendige Tests vorhanden und erfolgreich sind
- `python manage.py check` erfolgreich ist
- Migrationen geprüft wurden
- Ruff-Prüfungen erfolgreich sind
- relevante Dokumentation aktualisiert wurde
- keine Secrets, echten Nutzerdaten oder temporären Dateien enthalten sind
- der Autor den vollständigen Diff selbst geprüft hat

### Review und Merge

Standardprozess:

~~~text
Todo -> In Progress -> Review -> Done
~~~

Regeln:

- sobald mit der Umsetzung begonnen wird: Issue auf `In Progress`
- existiert ein zugehöriger offener PR: Issue auf `Review`, PR Ready for Review
- der Autor genehmigt den eigenen PR nicht als Ersatz für ein unabhängiges Review
- Review-Kommentare vor Merge klären oder nachvollziehbar auflösen
- CI muss vor Merge erfolgreich sein, sofern der PR CI auslöst
- wenn organisatorisch ein Review vorgesehen ist, mindestens eine andere Person reviewen lassen
- Standard-Merge-Strategie ist Squash Merge
- nach Merge Branch löschen
- nach Merge Abschluss im Issue dokumentieren und Status auf `Done` setzen
- gibt es für eine vollständig erledigte Aufgabe keinen notwendigen PR, darf das Issue nach erfüllter Definition of Done direkt auf `Done` gesetzt und geschlossen werden

Da technische Branch-Protection im verwendeten GitHub-Tarif nicht zwingend verfügbar ist, gelten diese Regeln unabhängig davon als verbindlicher Teamprozess.

## Code- und Dateikonventionen

### Sprache und Benennung

- Code-Identifier, Branch-Namen und Commit-Nachrichten sind Englisch.
- Benutzeroberfläche und fachliche Projektdokumentation sind grundsätzlich Deutsch.
- keine Mischformen wie `get_wohnung_data`
- Python-Variablen, Funktionen und Module: `snake_case`
- Klassen, Django-Modelle und Formulare: `PascalCase`
- Konstanten: `UPPER_SNAKE_CASE`
- URL-Namen sind beschreibend und innerhalb einer Django-App namespaced.
- fachliche Modelle werden im Singular benannt.
- Abkürzungen nur verwenden, wenn sie projektweit eindeutig und dokumentiert sind.

### Django-Struktur

- fachlicher Code liegt in der zuständigen Django-App
- keine globale `utils.py` als unspezifisches Sammelbecken
- wiederverwendbaren Code erst extrahieren, wenn tatsächliche Wiederverwendung vorliegt
- Templates app-bezogen strukturieren, zum Beispiel `templates/app_name/...`
- wiederverwendbare Template-Bausteine als klar benannte Partials ablegen
- Views, Forms, Models und Services nicht künstlich aufsplitten, wenn Django-Bordmittel ausreichen
- neue Django-App nur bei klar abgegrenzter fachlicher Verantwortung anlegen

### Datenbank und Migrationen

- bestehende bereits geteilte Migrationen nicht nachträglich umschreiben
- Schemaänderungen erhalten neue Migrationen
- destruktive oder irreversible Migrationen nur nach ausdrücklicher Freigabe
- Geldbeträge mit `DecimalField`, nicht mit Float-Typen
- Datums- und Zeitwerte timezone-aware behandeln
- fachlich zwingende Regeln möglichst zusätzlich mit Datenbank-Constraints absichern
- keine Geschäftslogik allein auf implizite Datenbankannahmen stützen
- Migrationen müssen reproduzierbar und im Repository enthalten sein

### Tests

- Testnamen beschreiben beobachtbares Verhalten
- Beispiel: `test_application_rejects_missing_email`
- Bugfixes erhalten nach Möglichkeit zuerst einen Test, der den Fehler reproduziert
- keine Tests ausschließlich für interne Implementierungsdetails
- keine Snapshot- oder End-to-End-Testframeworks ohne neue Entscheidung
- Tests dürfen keine Reihenfolge oder persistente lokale Daten voraussetzen

### Abhängigkeiten

Neue Runtime- oder Dev-Abhängigkeiten nur einführen, wenn Django, Python-Standardbibliothek, PostgreSQL oder UIkit den Bedarf nicht sinnvoll abdecken.

Vor Aufnahme einer Dependency prüfen:

- konkreter Nutzen
- Wartungsstatus
- Lizenz
- Sicherheits- und Updateaufwand
- Auswirkungen auf Docker-Image und CI
- ob eine kleine Eigenimplementierung mit Bordmitteln verständlicher wäre

Keine Bibliothek für triviale Hilfsfunktionen hinzufügen.

### Logging und Datenschutz

- kein `print()` für produktive Diagnose
- Python-/Django-Logging verwenden
- keine Passwörter, Tokens oder Secrets loggen
- keine hochgeladenen Dokumentinhalte loggen
- personenbezogene Daten nur loggen, wenn technisch zwingend erforderlich und auf das Minimum reduziert
- Fehlerausgaben dürfen keine vertraulichen Konfigurationswerte offenlegen

### Repository-Hygiene

Vor Abschluss jeder Änderung prüfen:

- `git status`
- `git diff`
- `git diff --check`
- keine IDE-Dateien
- keine temporären Dateien
- keine lokalen Datenbank-Dumps
- keine generierten Uploads
- keine `.env`-Datei
- keine echten Bewerber-, Mieter- oder Kundendokumente
- keine externen Kunden-, Arbeitgeber- oder Firmennamen ohne ausdrückliche Freigabe

Externe Referenzen, die nicht zum Projekt gehören, dürfen nicht versehentlich in Code, Dokumentation, Beispieldaten, Kommentaren oder Metadaten übernommen werden.

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

Bei Projekt-Board-Nutzung gilt grundsätzlich:

- `Todo`: noch nicht begonnen
- `In Progress`: aktive Umsetzung
- `Review`: Implementierung abgeschlossen, PR offen oder Review ausstehend
- `Done`: Definition of Done erfüllt und gegebenenfalls PR gemerged

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
- ein zugehöriger PR gemerged wurde, sofern einer erforderlich war
- der Abschluss im Issue dokumentiert wurde
- der Projektstatus auf `Done` gesetzt wurde, sofern das Issue in einem Projektboard geführt wird

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
- Force-Push
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
- keine Secrets, echten Nutzerdaten oder temporären Testdateien versehentlich versioniert wurden
- ein erforderlicher PR reviewed und gemerged wurde
- der Arbeitsbranch nach Merge gelöscht wurde
- das Issue aktualisiert, auf `Done` gesetzt und geschlossen wurde

## Abschlussbericht

~~~text
Ergebnis:
Geänderte Dateien:
Tests und Checks:
Dokumentation:
Aktualisiertes Issue:
Offene Punkte:
~~~
