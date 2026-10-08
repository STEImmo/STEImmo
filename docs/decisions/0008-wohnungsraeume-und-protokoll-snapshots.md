# ADR-0008: Wohnungsräume und Protokoll-Snapshots trennen

## Kontext

Raumnamen gehören zu einer konkreten Wohnung. Übergabeprotokolle müssen denselben Raum bei Ein- und Auszug vergleichen können, zugleich aber bei späteren Umbenennungen lesbar bleiben. Prüfpunktvorlagen werden wohnungsübergreifend wiederverwendet.

## Entscheidung

`Raum` ist ein wohnungsspezifischer Stamm mit UUID und innerhalb der Wohnung eindeutigem Namen. `Raumprotokoll` referenziert diesen Stamm und speichert beim Anlegen zusätzlich den damaligen Namen als unveränderlichen Snapshot. Ein referenzierter Raum wird durch `PROTECT` nicht gelöscht.

`Merkmal` bleibt eine globale Vorlage. Bereich und Bezeichnung sind Freitext, der Datentyp bleibt die vorhandene PostgreSQL-Enumeration und Optionen bleiben eine Liste einfacher Textwerte im bestehenden JSON-Feld.

Die Raumverwaltung steht unter dem Formular für Wohnungsstammdaten, Mieten,
Zähler und Schlüssel. Ihre Löschaktionen verwenden eigenständige POST-Formulare
außerhalb des Wohnungsformulars (#78). So enthält die Seite keine verschachtelten
Formulare, und das Löschen eines Raums speichert keine anderen Wohnungsangaben.
Der bestehende Löschschutz referenzierter Räume bleibt erhalten.

Im offenen Protokoll unterscheidet eine eigene, serverseitig auf dieses Protokoll
begrenzte Liste `removed_rooms` die Entfernung einer ganzen gespeicherten Raumkarte
von der Löschung einzelner Prüfpunkte (#83). Jede Karte behält dafür ihre stabile
Raumprotokoll-ID, auch bei leerem Inhalt oder geändertem Raumselektor. Der Entwurf
speichert diese ID und die ausdrückliche Raumlöschung separat. Ältere Entwürfe
ohne diese Angabe behalten ihre bisherige Bedeutung als Prüfpunktänderungen.
Die vollständige Raumlöschung erfolgt innerhalb derselben gesperrten
Protokolltransaktion wie die übrigen Änderungen und verwendet die bestehende
Fotobereinigung. Speicherfehler rollen Raum und Bereinigungsaufträge zurück;
Dateien werden erst nach erfolgreichem Commit entfernt. Wohnungsraumstammdaten
und nicht ausdrücklich entfernte Raumvorgänge bleiben erhalten.
Zum Entfernen vorgemerkte Raumvorgänge werden beim vorgezogenen Prüfpunkt- und
Fotoabgleich nicht als Bestand verwendet. Eine neue Karte desselben Wohnungsraums
kann dadurch vollständig neu erfasst werden, ohne Fotos gegen die gerade
entfernten Dateien zu deduplizieren.

Die Migration legt für historische Raumprotokolle je Wohnung und Namen einen Raumstamm an. Mehrfach vorhandene gleichnamige Räume desselben Protokolls müssen vor der Migration fachlich bereinigt werden.

Inline-Prüfpunkte übernehmen die gültige Raumauswahl der vorangehenden Zeile auch
bei anderen Feldfehlern. Erst danach wird die raumbezogene Prüfung ausgeführt.
Eine ungültige Raumauswahl unterbricht die Vererbung, damit Folgezeilen keinem
vorherigen Raum versehentlich zugeordnet werden.

## Konsequenzen

Die erneute Anzeige nach Formularfehlern gruppiert Raumkarten zusätzlich anhand
ihrer Raumprotokoll-ID. Ein entfernter gespeicherter Raum und eine neue Ersatzkarte
desselben Wohnungsraums bleiben dadurch getrennt, einschließlich sichtbarer Fehler
der Ersatzkarte. Neue Prüfpunkte einer bestehenden Karte übernehmen im Browser
deren Raumprotokoll-ID; neue Raumkarten erhalten keine alte Identität.

- Es gibt weder ein globales Raum-Enum noch ein Küchen-Sondermodell.
- Vergleiche erfolgen über die Raum-ID; historische Anzeigen verwenden den Namens-Snapshot.
- Globale Merkmalvorlagen können unabhängig von Wohnungen gepflegt und in jedem Raumprotokoll verwendet werden.
