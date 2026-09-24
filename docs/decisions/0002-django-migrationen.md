# ADR-0002: Django-Migrationen als Quelle der Datenbankstruktur

- Status: Accepted
- Datum: 2026-09-22
- Geltungsbereich: STEImmo-Django-Monolith

## Kontext

Die PostgreSQL-Datenbank soll beim ersten Compose-Start eine einheitliche Struktur erhalten. Gleichzeitig sollen spätere Änderungen die bestehenden Entwicklungsdaten nicht durch ein manuelles Löschen des Volumes zurücksetzen.

## Entscheidung

Die fachliche Datenbankstruktur wird in Django-Modellen beschrieben und über versionierte Django-Migrationen verwaltet. Der Web-Container führt in seinem Entrypoint nach erfolgreicher PostgreSQL-Health-Prüfung automatisch `python manage.py migrate --noinput` aus.

Die Compose-Konfiguration stellt PostgreSQL bereit; sie enthält keine zweite, parallele SQL-Quelle für das fachliche Schema. Neue Änderungen werden mit `makemigrations` erzeugt und beim nächsten Containerstart angewendet.

Die im ER-Modell festgelegten Status- und Merkmalswerte werden als echte PostgreSQL-Enum-Typen angelegt. Neue Enum-Werte benötigen deshalb zusätzlich eine explizite Migration mit `ALTER TYPE ... ADD VALUE`; reine Änderungen an `TextChoices` aktualisieren einen bestehenden PostgreSQL-Enum-Typ nicht automatisch.

Die Zuordnung `BewerbungStellplatz` verwendet entsprechend dem ER-Modell einen zusammengesetzten Primärschlüssel aus Bewerbung und Stellplatz. Django 5.2 unterstützt diese Primärschlüssel; Modelle mit zusammengesetztem Primärschlüssel können derzeit jedoch nicht im Django-Admin registriert werden. Die Zuordnung wird deshalb zunächst über die normale ORM-Schicht verwaltet.

## Begründung

- Django-Migrationen unterstützen sowohl die initiale Erstellung als auch inkrementelle Änderungen.
- Bestehende Daten bleiben bei kompatiblen Migrationen erhalten.
- Modelle, Anwendungscode und Datenbankstruktur bleiben im Django-Monolithen versioniert.
- Eine zweite SQL-Initialisierung würde zu zwei konkurrierenden Quellen der Wahrheit führen.

## Konsequenzen

- Die konkrete ER-Struktur muss als Django-Modelle und Migrationen umgesetzt werden.
- Neue Migrationen müssen geprüft und versioniert committed werden.
- Neue Werte in einem PostgreSQL-Enum benötigen eine eigene, nicht destruktive Enum-Migration.
- Destruktive oder nicht automatisch verlustfreie Änderungen erfordern weiterhin eine bewusste Migration und gegebenenfalls eine Datensicherung.
- Das PostgreSQL-Volume muss für normale Strukturänderungen nicht gelöscht werden.
