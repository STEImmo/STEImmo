# ADR-0001: Finaler MAO-Stack

- Status: Accepted
- Datum: 2026-09-22
- Geltungsbereich: STEImmo-Uni-MVP

## Kontext

Das Projekt ist eine kleine Webanwendung für eine Immobiliengesellschaft. Immobilien sollen veröffentlicht und verwaltet werden. Studierende sollen suchen, filtern, Immobilien ansehen und Anfragen stellen können. Bewertungen, Termine und Dokumentenupload gehören zum vorgesehenen MVP-Umfeld.

Das Team besteht aus vier Entwicklern und einer Person mit Schwerpunkt Projektmanagement. Die Entwicklungszeit beträgt ungefähr acht Wochen. Die Anwendung soll auf dem Uni-Server laufen und später ohne grundlegenden Plattformumbau auf VORNIS-Kundenhardware portierbar sein.

Die wichtigsten Kriterien sind:

- geringe Gesamtkomplexität
- schneller Einstieg für vier Entwickler
- fertige, begrenzende UI-Komponenten
- lokales Entwickeln und einfaches Hosting
- gute Wartbarkeit und Portierbarkeit

## Entscheidung

Wir verwenden folgenden Stack:

| Bereich | Entscheidung |
|---|---|
| Sprache | Python 3.13 |
| Backend | Django 5.2 LTS |
| Architektur | Ein Django-Monolith |
| UI | UIkit mit projektweiter Komponenten-Whitelist |
| Rendering | Serverseitige Django Templates |
| JavaScript | UIkit JavaScript, ergänzend Vanilla JavaScript |
| Datenbank | PostgreSQL 17 |
| Betrieb | Docker Compose |
| Produktionsserver | Gunicorn |
| Tests | Django Test Framework |
| Codequalität | Ruff |
| Versionsverwaltung | GitHub |

## Begründung

### Django statt Java/Spring

Django deckt Authentifizierung, ORM, Formulare, Admin-Oberfläche, Migrationen und serverseitiges Rendering bereits integriert ab. Das passt direkt zum CRUD-, Such- und Anfrageumfang des MVP.

Java mit Spring Boot wäre technisch geeignet, erzeugt für diesen Umfang aber mehr Konfigurations- und Integrationsaufwand. Django reduziert dadurch die Time-to-MVP, ohne die spätere Portierbarkeit wesentlich einzuschränken.

### Server-rendered statt Single-Page-App

Eine separate React- oder Vue-Anwendung würde eine zusätzliche Toolchain, API-Schicht und Deployment-Grenze einführen. Für die geplante Webapp reichen Django Templates, UIkit JavaScript und wenige gezielte Vanilla-JavaScript-Interaktionen.

### UIkit statt freier UI-Entwicklung

UIkit bietet fertige Layout-, Formular-, Navigations-, Modal-, Upload- und Feedback-Komponenten. Die Whitelist begrenzt gestalterische Freiheiten und beschleunigt die gemeinsame UI-Entscheidung.

### PostgreSQL statt SQLite

PostgreSQL ist für parallele Zugriffe, Suchabfragen, produktiven Betrieb und spätere Weiterentwicklung geeigneter. SQLite wird nicht als Produktionsdatenbank verwendet.

### Docker Compose

Docker Compose sorgt dafür, dass alle vier Entwickler und der Uni-Server dieselbe grundlegende Laufzeitumgebung verwenden. Das reduziert lokale Abweichungen und erleichtert späteres Self-Hosting bei VORNIS.

### Kein Kubernetes

Kubernetes würde für einen einzelnen Monolithen mit einer PostgreSQL-Datenbank zusätzlichen Betriebsaufwand ohne MVP-Nutzen erzeugen.

## Konsequenzen

Positiv:

- geringe Anzahl an Laufzeitkomponenten
- schnelle Entwicklung und Einarbeitung
- konsistentes UI
- reproduzierbare lokale und serverseitige Umgebung
- portierbare Anwendung ohne Cloud-Zwang

Negativ:

- Django Templates koppeln Darstellung und Backend stärker als eine separate SPA
- UIkit begrenzt individuelle Gestaltung bewusst
- Docker muss auf den Entwicklungsrechnern und dem Uni-Server verfügbar sein
- bei starkem Echtzeit- oder Offlinebedarf wäre eine spätere Neubewertung nötig

## Nicht Bestandteil dieser Entscheidung

Die folgenden Punkte werden erst mit den konkreten MVP-Anforderungen festgelegt:

- genaue Django-App-Struktur innerhalb des Monolithen
- fachliches Datenmodell
- Rollen- und Berechtigungsmatrix
- konkrete Upload- und Kalenderprozesse
- Reverse Proxy, TLS und Domain des Uni-Servers
- CI/CD-Workflow

Diese Punkte dürfen den festgelegten Stack nicht ohne neues ADR erweitern oder aufspalten.

## Neubewertung

Der Stack wird nur neu bewertet, wenn sich mindestens eine zentrale Randbedingung ändert, zum Beispiel:

- kein Docker auf dem Zielserver möglich
- deutlich größerer Funktionsumfang
- verbindliche Integration in bestehende Java-Infrastruktur
- Anforderungen an Echtzeit, Offlinebetrieb oder extreme Skalierung
