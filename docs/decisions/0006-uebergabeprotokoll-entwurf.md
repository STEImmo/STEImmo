# ADR-0006: Lokaler Entwurf für Übergabeprotokolle

- Status: Superseded by ADR-0007
- Datum: 2026-09-28
- Geltungsbereich: STEImmo-Django-Monolith

## Kontext

Das Anlegen und Bearbeiten eines Übergabeprotokolls umfasst zahlreiche Angaben,
Räume, Prüfpunkte und Schlüsselpositionen. Ein versehentliches Neuladen der
Seite oder ein temporär nicht erreichbarer Server darf diese noch nicht
abgeschlossenen Eingaben nicht verlieren lassen.

## Entscheidung

Die Anlege- und Bearbeitungsmaske speichert den aktuellen Eingabestand nach
jeder Änderung lokal im Browser. Beim erneuten Öffnen der gleichen Maske wird
ein höchstens sieben Tage alter Entwurf zum bewussten Wiederherstellen oder
Verwerfen angeboten. Der Entwurf umfasst auch dynamisch hinzugefügte Räume,
Prüfpunkte und Schlüsselpositionen.

Unvollständige oder fachlich noch ungültige Daten werden nicht in der Datenbank
gespeichert. Nach dem erfolgreichen Speichern des Protokolls wird der passende
lokale Entwurf entfernt.

## Konsequenzen

- Die letzte Eingabe bleibt bei einem Seiten- oder Serverfehler auf demselben
  Gerät und im selben Browser wiederherstellbar.
- Es entsteht keine Datenbankmigration und kein zusätzlicher Entwurfsstatus
  für fachlich unvollständige Protokolle.
- Lokale Entwürfe sind nicht geräteübergreifend verfügbar und können über die
  Oberfläche verworfen werden.
