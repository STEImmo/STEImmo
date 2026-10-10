# ADR-0012: Alt/Neu-Vergleich im Auszugsprotokoll

## Kontext

Die Fotos und Feststellungen aus dem Einzug sollen beim Auszug direkt mit
dem aktuellen Zustand vergleichbar sein. Ein Prüfpunkt kann jedoch in einem
der beiden Protokolle fehlen.

## Entscheidung

Gleiche Prüfpunkte werden über denselben Stammraum und dasselbe Merkmal
zugeordnet und als zwei UIkit-Karten nebeneinander gezeigt: Einzug links,
Auszug rechts. Auf kleinen Bildschirmen werden die Karten untereinander
angeordnet.

Beim Anlegen oder Bearbeiten eines Auszugsprotokolls werden die Zählerstände
des passenden Einzugs neben den neuen Eingabefeldern angezeigt. Die Differenz
„Auszug neu minus Einzug alt“ wird im Browser direkt nach jeder Eingabe
berechnet. Die gespeicherten Werte bleiben unverändert; die Differenz ist nur
eine Eingabehilfe.

Prüfpunkte ohne Gegenstück bleiben sichtbar, werden aber ausdrücklich als
fehlendes Gegenstück gekennzeichnet. Sie werden nicht mit einem beliebigen
anderen Prüfpunkt zusammengeführt.

Beim dynamischen Nachladen nach Änderungen an Wohnung, Person oder
Übergabezeitpunkt darf nur die neueste Anfrage den Vergleich aktualisieren.
Nach dem vollständigen Laden der Antwort wird zusätzlich geprüft, ob die
angefragte Auswahl noch den aktuellen Eingaben entspricht. Verspätete Antworten
werden verworfen, damit Referenz und Differenzen zum sichtbaren Formular passen.

## Konsequenzen

- Fotos, Text und Zusatzangaben bleiben fachlich korrekt zugeordnet.
- Der Vergleich ist auf großen und kleinen Bildschirmen verständlich.
- Fehlende Prüfpunkte beim Auszug werden erkennbar und können gezielt
  nacherfasst werden.
