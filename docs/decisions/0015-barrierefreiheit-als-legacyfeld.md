# ADR-0015: Barrierefreiheit als Legacyfeld beibehalten

- Status: Accepted
- Datum: 2026-10-05
- Geltungsbereich: STEImmo-Django-Monolith

## Kontext

[Userstory #53](https://github.com/STEImmo/STEImmo/issues/53) beendet die Erfassung
des Merkmals „Barrierefrei“ in der Wohnungsverwaltung. Das Frontend soll das
Merkmal auch nicht mehr als Suchfilter nutzen oder in Suchergebnissen anzeigen.
Historische Werte und die bestehende Datenbankstruktur sollen erhalten bleiben.

## Entscheidung

`WohnungForm` führt `barrierefrei` nicht mehr in seiner expliziten Feldliste.
Das Wohnungsformular zeigt das Feld nicht mehr an. Zusätzlich übermittelte
Formularwerte werden dadurch weder verarbeitet noch gespeichert.

`ApartmentSearchForm` enthält das Feld ebenfalls nicht mehr. Die öffentliche
Suchansicht wertet einen zusätzlich übermittelten `barrierefrei`-Parameter weder
zur Validierung noch zur Filterung aus. Alte Suchlinks funktionieren weiter;
andere Suchfilter bleiben wirksam. Die Wohnungskarten zeigen das Legacymerkmal
nicht mehr an.

`Wohnung.barrierefrei` und `Bewerbung.barrierefreiheit_benoetigt` bleiben
unverändert im Datenmodell. Es wird keine Migration für diese Änderung erzeugt.
Backend-Testdaten dürfen weiterhin Werte für `barrierefrei` setzen.

## Konsequenzen

- Beim Bearbeiten einer Wohnung bleibt ihr gespeicherter Legacywert erhalten,
  auch wenn eine Anfrage das Feld zusätzlich übermittelt.
- Neue Wohnungen erhalten den bestehenden Modellstandard `False`.
- Die öffentliche Suche nutzt die Legacywerte nicht mehr für Filterung oder
  Anzeige.
- Historische Daten werden nicht bereinigt.
