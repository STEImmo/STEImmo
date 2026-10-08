# ADR-0004: Stellplatzmiete im Stellplatzstamm führen

- Status: Accepted
- Datum: 2026-09-29
- Geltungsbereich: STEImmo-Django-Monolith

## Kontext

Ein Stellplatz wird unabhängig von einer Wohnung vermietet und hat daher einen eigenen Mietbetrag. Die bisherige Ablage des Betrags ausschließlich in `stellplatz_zuordnung` verhindert die Pflege einer Stellplatzmiete, solange kein Stellplatz einer Wohnung zugeordnet ist.

## Entscheidung

`stellplatz.miete` ist der nicht-negative Mietbetrag des physischen Stellplatzes. `stellplatz_zuordnung` enthält nur noch die optionale aktuelle Beziehung zwischen Stellplatz und Wohnung.

Die additive Migration übernimmt die bisherigen Zuordnungsmieten in den Stellplatzstamm und entfernt den doppelten Betrag anschließend aus der Zuordnungstabelle.

Beim Speichern eines vorhandenen Stellplatzes wird nach der Formularprüfung die
Stellplatzzeile innerhalb der Speichertransaktion gesperrt und ihre aktuelle
Wohnungszuordnung erneut gelesen (#79). Auch zwei Anfragen, die zunächst keine
Zuordnung vorfinden, werden so wie nacheinander ausgeführte Bearbeitungen
verarbeitet. Die zuletzt verarbeitete gültige Auswahl bestimmt die Zuordnung.
Stammdaten und Zuordnung werden gemeinsam gespeichert; ein verbleibender
Datenbankkonflikt rollt beide zurück und erscheint als verständlicher Fehler
am Wohnungsfeld. Der bestehende Unique-Constraint bleibt die zusätzliche
Datenbankgrenze. Dafür ist keine neue Migration erforderlich.

## Konsequenzen

- Stellplätze lassen sich mit Miete anlegen und führen, ohne einer Wohnung zugeordnet zu sein.
- Eine Zuordnung weist einen Stellplatz einer Wohnung zu, verändert aber nicht dessen Miete.
- Die Miete eines Stellplatzes ist unabhängig von Kalt-, Warmmiete und Kaution der Wohnung.
