# ADR-0009: Fotos an bestehenden Übergabe-Prüfpunkten

## Kontext

`RaumMerkmal` dokumentiert bereits die Feststellung zu einem Prüfpunkt eines
Raumprotokolls. Für die Dokumentation auffälliger Feststellungen werden Fotos
benötigt, ohne eine zweite, parallele Mängeldomäne zu schaffen.

## Entscheidung

Fotos werden als `RaumMerkmalFoto` direkt einem bestehenden `RaumMerkmal`
zugeordnet. Ein Prüfpunkt kann mehrere Fotos haben. Die Feststellung im
bestehenden JSON-Feld `wert` bleibt die fachliche Beschreibung.

Die Bilddateien liegen im bestehenden Django-Media-Volume; PostgreSQL speichert
nur die Zuordnung, den durch Django erzeugten nicht erratbaren Dateipfad,
verifizierten Content-Type und die Dateigröße. Die Bildauslieferung erfolgt
ausschließlich über eine staff-geschützte Django-Ansicht. Akzeptiert werden
JPEG, PNG und WebP mit höchstens 8 MiB je Datei und zehn Fotos je Prüfpunkt.

Nach der Bestätigung eines Protokolls sind Fotos wie die übrigen Prüfpunkte
nicht mehr veränderbar.

## Konsequenzen

- Es gibt kein neues Modell für Mängel und keine doppelte Erfassung.
- Fotos bleiben fachlich genau einer bereits erfassten Feststellung zugeordnet.
- Das persistente Docker-Media-Volume bewahrt die Bilddateien über
  Container-Neustarts hinweg.
