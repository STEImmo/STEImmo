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

Die vier Zählerstände und Zusatzablesungen der Heizung haben im Formular
jeweils genau ein Eingabefeld für beide Übergabearten. Beim Auszug werden
die Vergleichsspalten eingeblendet. Doppelte Felder je Übergabeart werden
vermieden, weil sie Pflichtfeldvalidierung, Übertragung und
Entwurfswiederherstellung mehrdeutig machen können (Issue #110).
Eingaben ausschließlich für die inaktive Übergabeart werden ausgeblendet
und deaktiviert; die fachliche Validierung bleibt im Django-Formular.

Prüfpunkte ohne Gegenstück bleiben sichtbar, werden aber ausdrücklich als
fehlendes Gegenstück gekennzeichnet. Sie werden nicht mit einem beliebigen
anderen Prüfpunkt zusammengeführt.

## Konsequenzen

- Fotos, Text und Zusatzangaben bleiben fachlich korrekt zugeordnet.
- Der Vergleich ist auf großen und kleinen Bildschirmen verständlich.
- Fehlende Prüfpunkte beim Auszug werden erkennbar und können gezielt
  nacherfasst werden.
