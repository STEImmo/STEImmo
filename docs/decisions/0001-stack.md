# ADR-0001: Finaler MAO-Stack

- Status: Accepted
- Datum: 2026-09-22
- Geltungsbereich: STEImmo-Uni-MVP

## Kontext

Das Projekt ist eine kleine Webanwendung für eine Immobiliengesellschaft. Verwaltet wird eine einzelne Immobilie mit 25 Einheiten.

Studierende sollen Einheiten suchen, filtern, ansehen, Anfragen stellen und sich bewerben können. Dokumentenupload und Datepicker für Datumsangaben gehören zum MVP. Bewertungen und die Verwaltung weiterer Immobilien sind nicht Bestandteil des MVP.

Das Team besteht aus vier Entwicklern und einer Person mit Schwerpunkt Projektmanagement. Die Entwicklungszeit beträgt ungefähr acht Wochen. Die Anwendung soll auf dem Uni-Server laufen und später ohne grundlegenden Plattformumbau auf kundeneigene Hardware portierbar sein.

Die wichtigsten Kriterien sind:

- geringe Gesamtkomplexität
- schneller Einstieg für vier Entwickler
- fertige, begrenzende UI-Komponenten
- lokales Entwickeln und einfaches Hosting
- gute Wartbarkeit und Portierbarkeit
- nachvollziehbare Tests und Issue-Dokumentation

## Entscheidung

Wir verwenden folgenden Stack:

| Bereich | Entscheidung |
|---|---|
| Sprache | Python 3.13 |
| Backend | Django 5.2 LTS |
| Architektur | Ein Django-Monolith |
| UI | UIkit 3.25.24 mit projektweiter Komponentenpalette |
| Rendering | Serverseitige Django Templates |
| JavaScript | UIkit JavaScript, ergänzend minimales Vanilla JavaScript |
| Datenbank | PostgreSQL 18.6 |
| Datenbanktreiber | psycopg 3 |
| Dateien | Django Media-Storage mit persistentem Volume |
| Betrieb | Docker Compose |
| Produktionsserver | Gunicorn hinter dem Uni-Reverse-Proxy |
| Tests | Django Test Framework mit pragmatischem TDD |
| Codequalität | Ruff |
| Versionsverwaltung | GitHub |
| CI | Schlanker GitHub-Actions-Workflow |

## Entwicklungsregeln

Die Entwicklung folgt diesen MAO-Prinzipien:

- KISS: einfache Lösungen bevorzugen
- YAGNI: keine Funktionen für hypothetische Anforderungen
- pragmatisches DRY: keine vorzeitigen Abstraktionen
- Vertical Slices: Funktionen vollständig durch alle betroffenen Schichten umsetzen
- TDD: Test, minimale Implementierung, Refactoring
- GitHub Issues als verbindliche Aufgaben- und Fortschrittsquelle

TDD gilt insbesondere für Such- und Filterlogik, Formulare, Berechtigungen, Statuswechsel, Uploads, Anfragen und Bewerbungen. Für reine CSS- und Template-Gestaltung werden keine künstlichen Tests erstellt.

## Begründung

### Django statt Java/Spring

Django deckt Authentifizierung, ORM, Formulare, Admin-Oberfläche, Migrationen und serverseitiges Rendering bereits integriert ab. Das passt direkt zum CRUD-, Such- und Anfrageumfang des MVP.

Java mit Spring Boot wäre technisch geeignet, erzeugt für diesen Umfang aber mehr Konfigurations- und Integrationsaufwand. Django reduziert dadurch die Time-to-MVP, ohne die spätere Portierbarkeit wesentlich einzuschränken.

### Server-rendered statt Single-Page-App

Eine separate React- oder Vue-Anwendung würde eine zusätzliche Toolchain, API-Schicht und Deployment-Grenze einführen. Für die geplante Webapp reichen Django Templates, UIkit JavaScript und wenige gezielte Vanilla-JavaScript-Interaktionen.

### UIkit statt freier UI-Entwicklung

UIkit bietet fertige Layout-, Formular-, Navigations-, Modal-, Upload- und Feedback-Komponenten. Die verbindliche Komponentenpalette begrenzt gestalterische Freiheiten und beschleunigt die gemeinsame UI-Entscheidung.

Der Datepicker wird als natives Datumsfeld umgesetzt. Ein Kalender-Framework wird nicht eingeführt.

### PostgreSQL statt SQLite

PostgreSQL ist für parallele Zugriffe, Suchabfragen, produktiven Betrieb und spätere Weiterentwicklung geeigneter. SQLite wird nicht als Produktionsdatenbank verwendet.

### Docker Compose

Docker Compose sorgt dafür, dass alle vier Entwickler und der Uni-Server dieselbe grundlegende Laufzeitumgebung verwenden. Das reduziert lokale Abweichungen und erleichtert späteres Self-Hosting auf kundeneigener Infrastruktur.

### Kein Kubernetes

Kubernetes würde für einen einzelnen Monolithen mit einer PostgreSQL-Datenbank zusätzlichen Betriebsaufwand ohne MVP-Nutzen erzeugen.

## Konsequenzen

Positiv:

- geringe Anzahl an Laufzeitkomponenten
- schnelle Entwicklung und Einarbeitung
- konsistentes UI
- reproduzierbare lokale und serverseitige Umgebung
- portierbare Anwendung ohne Cloud-Zwang
- nachvollziehbarer Entwicklungs- und Testprozess

Negativ:

- Django Templates koppeln Darstellung und Backend stärker als eine separate SPA
- UIkit begrenzt individuelle Gestaltung bewusst
- Docker muss auf den Entwicklungsrechnern und dem Uni-Server verfügbar sein
- bei starkem Echtzeit- oder Offlinebedarf wäre eine spätere Neubewertung nötig

## Nicht Bestandteil dieser Entscheidung

Folgende Punkte werden innerhalb des festgelegten Rahmens konkretisiert:

- genaue Django-App-Struktur innerhalb des Monolithen
- fachliches Datenmodell
- Rollen- und Berechtigungsmatrix
- konkrete Upload-Limits und Backup-Details
- genaue Reverse-Proxy-, TLS- und Domain-Konfiguration
- konkrete GitHub-Actions-Konfiguration

Diese Konkretisierungen dürfen den festgelegten Stack nicht ohne neues ADR erweitern oder aufspalten.

## Neubewertung

Der Stack wird nur neu bewertet, wenn sich mindestens eine zentrale Randbedingung ändert, zum Beispiel:

- kein Docker auf dem Zielserver möglich
- deutlich größerer Funktionsumfang
- verbindliche Integration in bestehende Java-Infrastruktur
- Anforderungen an Echtzeit, Offlinebetrieb oder extreme Skalierung
- grundlegende Änderung des MVP-Umfangs
