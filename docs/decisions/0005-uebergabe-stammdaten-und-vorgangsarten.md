# ADR-0005: Stammdaten und Vorgangsarten im Übergabeprotokoll

- Status: Accepted
- Datum: 2026-09-26
- Geltungsbereich: STEImmo-Django-Monolith

## Kontext

Die Wohnung enthält den Stammdatensatz der Zählernummern und des allgemeinen
Schlüsselbestands. Das Übergabeprotokoll dokumentiert dagegen den Zustand zu
einem konkreten Zeitpunkt. Die Eingabemaske hatte Zählernummern und eine freie
Anzahl von Anlagenblättern abgefragt. Zudem vermischte sie Einzugs- und
Auszugsangaben.

## Entscheidung

Zählernummern werden ausschließlich aus der ausgewählten Wohnung gelesen und
beim Speichern als Momentaufnahme in das Protokoll übernommen. Die Werte können
in der Übergabemaske nicht verändert werden; fehlt eine Nummer im Stamm, kann
kein Protokoll angelegt werden.

Einzugsprotokolle führen die Nachweise für Kaution und erste Miete. Auszugs-
protokolle führen die zukünftige Anschrift sowie optionale Nachbesserungen mit
Frist. Nicht zur Vorgangsart gehörende Angaben werden serverseitig geleert.

Raumprotokolle und ihre Prüfpunkte sowie Schlüsselpositionen werden als
untergeordnete Daten direkt im Anlege- und Bearbeitungsformular erfasst.
Schlüsselpositionen werden mit den Daten der gewählten Wohnung vorbelegt und
als protokollspezifische Momentaufnahme gespeichert.

Die manuelle Anzahl von Anlagenblättern wird nicht mehr in der Oberfläche
verwendet: Sie hatte keine prüfbare Quelle. Die Projektvorgabe verlangt Foto-
und Mängeldokumentation. Eine Dateiablage wird erst mit einem eigenen,
zugriffsgeschützten Upload-Konzept umgesetzt, das Berechtigungen, Dateitypen,
Größenlimits und die Zuordnung zu Prüfpunkten verbindlich festlegt.

## Konsequenzen

- Zählernummern bleiben konsistent mit den Wohnungsstammdaten.
- Einzugs- und Auszugsvorgänge enthalten nur fachlich passende Angaben.
- Räume, Prüfpunkte und Schlüssel können ohne Seitenwechsel mit dem Protokoll
  gespeichert werden.
- Ein ungesicherter Zähler für nicht vorhandene Anlagen wird nicht vorgetäuscht.
