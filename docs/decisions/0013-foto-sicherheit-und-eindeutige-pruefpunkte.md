# ADR-0013: Verifizierte Foto-Typen und eindeutige Prüfpunkte

## Kontext

Prüfpunktfotos werden über Django ausgeliefert und beim Auszug über Raum und
Merkmal dem Einzugszustand gegenübergestellt. Der vom Browser gelieferte
MIME-Typ ist dabei nicht vertrauenswürdig. Außerdem waren dieselben
Raum-/Merkmal-Kombinationen in einem Raumprotokoll mehrfach möglich, wodurch
der Alt/Neu-Vergleich einen Eintrag stillschweigend überschreiben konnte.

## Entscheidung

JPEG, PNG und WebP werden weiterhin mit `ImageField` inhaltlich geprüft. Der
gespeicherte und ausgelieferte MIME-Typ wird ausschließlich aus dem von Pillow
verifizierten Bildformat abgeleitet. Auch historische Bilddateien werden beim
Abruf erneut geprüft und nur mit einem festen erlaubten Bildtyp ausgeliefert.

Die Mitarbeiterberechtigung schützt einheitlich die Foto-Oberfläche,
Einzugsreferenzen sowie Upload-, Anzeige- und Lösch-Endpunkte.
Damit ersetzt diese Entscheidung die staff-spezifische Schutzbeschreibung aus
ADR-0009.

Ein Raumprotokoll darf pro Merkmal nur einen Prüfpunkt enthalten. Die
Eingabeformulare zeigen bei einer doppelten Kombination eine Feldfehlermeldung.
Eine Datenbank-Constraint sichert diese Regel für alle Schreibwege. Die
Migration beendet sich mit einem konkreten Hinweis, falls historische Daten
Dubletten enthalten; Belegfotos werden nicht automatisch gelöscht.

## Konsequenzen

- Client-seitig deklarierte Typen können nicht mehr zur HTML-Auslieferung von
  Bilddateien führen.
- Mitarbeiter erhalten die gleiche Foto-Bedienung, die ihre geschützten
  Endpunkte erlauben.
- Alt/Neu-Referenzen bleiben eindeutig; vorhandene Daten werden nicht
  stillschweigend verändert.
