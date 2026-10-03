# ADR-0010: Einzugsfotos als Referenz beim Auszug

## Kontext

Beim Auszug soll der dokumentierte Zustand beim Einzug mit dem aktuellen
Prüfpunkt vergleichbar sein. Die Fotos sind bereits dem jeweiligen
`RaumMerkmal` des Einzugsprotokolls zugeordnet.

## Entscheidung

Für ein Auszugsprotokoll wird das zeitlich jüngste, bereits bestätigte
Einzugsprotokoll derselben Wohnung und beteiligten Person verwendet, dessen
Übergabezeitpunkt nicht nach dem Auszug liegt. Wenn bei nachträglich
dokumentierten Protokollen kein solcher zeitlicher Vorgänger vorliegt, wird
als Fallback das jüngste bestätigte Einzugsprotokoll derselben Person und
Wohnung verwendet. Fotos erscheinen nur bei Prüfpunkten mit demselben
Stammraum und demselben Merkmal.

Die Fotos werden nicht kopiert und keine neue Zuordnung angelegt. Sie bleiben
beim Einzugsprüfpunkt gespeichert und werden über ihre bestehende geschützte
Auslieferungsadresse referenziert. In der Oberfläche werden sie als anklickbare
Vorschaubilder mit einem gemeinsamen, nativen Bilddialog im UIkit-Stil
angezeigt. Dieser Dialog wird mit kleinem Vanilla JavaScript gesteuert, damit
das Öffnen eines Fotos unabhängig von den anderen Fotogruppen bleibt.

## Konsequenzen

- Die historische Beweiskette bleibt unverändert: Ein Foto gehört weiterhin
  genau zu dem Prüfpunkt, bei dem es erstellt wurde.
- Es wird nur ein bestätigtes Einzugsprotokoll derselben beteiligten Person
  als Vergleichsbasis verwendet.
- Fotos aus anderen Räumen, anderen Merkmalen oder älteren Einzügen werden
  nicht als aktueller Referenzzustand angezeigt.
