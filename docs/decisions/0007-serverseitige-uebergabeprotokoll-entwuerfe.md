# ADR-0007: Serverseitige Entwürfe für Übergabeprotokolle

- Status: Accepted
- Datum: 2026-09-28
- Geltungsbereich: STEImmo-Django-Monolith
- Ergänzt: ADR-0006

## Kontext

Lokale Browserentwürfe schützen Eingaben bei einem Seitenfehler, erscheinen
jedoch nicht in der Übersicht der Übergabeprotokolle. Ein angefangener Vorgang
soll dort aktiv fortgesetzt werden können.

## Entscheidung

Zusätzlich zum lokalen Browserentwurf wird der Eingabestand nach jeder Änderung
serverseitig in `ProtokollEntwurf` gespeichert. Der Entwurf wird über die
Browser-Sitzung zugeordnet, damit in der Übersicht nur die eigenen, noch nicht
abgeschlossenen Entwürfe erscheinen. Die Übersicht bietet „Entwurf fortsetzen"
und „Entwurf löschen".

Unvollständige Daten bleiben ausschließlich im Entwurf und erzeugen kein
fachlich wirksames `Protokoll`. Nach dem erfolgreichen Speichern wird der
zugehörige Entwurf server- und browserseitig gelöscht.

## Konsequenzen

- Entwürfe sind in der Übersicht desselben Browsers sichtbar und gezielt
  fortsetzbar.
- Bei einer kurzzeitig nicht erreichbaren Serververbindung bleibt der lokale
  Browserentwurf als zusätzliche Absicherung erhalten.
- Ohne Benutzerkonto sind Entwürfe nicht geräteübergreifend; ihre Zuordnung
  erfolgt bewusst über die Browser-Sitzung.
