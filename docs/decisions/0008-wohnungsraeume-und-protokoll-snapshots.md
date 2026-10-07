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

Die Migration legt für historische Raumprotokolle je Wohnung und Namen einen Raumstamm an. Mehrfach vorhandene gleichnamige Räume desselben Protokolls müssen vor der Migration fachlich bereinigt werden.

## Konsequenzen

- Es gibt weder ein globales Raum-Enum noch ein Küchen-Sondermodell.
- Vergleiche erfolgen über die Raum-ID; historische Anzeigen verwenden den Namens-Snapshot.
- Globale Merkmalvorlagen können unabhängig von Wohnungen gepflegt und in jedem Raumprotokoll verwendet werden.
