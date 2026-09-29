# ADR-0003: Stellplatzstamm und Wohnungszuordnung trennen

- Status: Accepted
- Datum: 2026-09-28
- Geltungsbereich: STEImmo-Django-Monolith

## Kontext

Ein Stellplatz ist ein eigenständiges physisches Objekt. Seine aktuelle Vermietung und der dafür vereinbarte Betrag beziehen sich jedoch auf eine Wohnung. Die bisherige direkte Beziehung in `stellplatz` vermischt beide Ebenen und verhindert eine unvermietete Führung oder spätere Umzuordnung.

## Entscheidung

`stellplatz` führt nur die unabhängigen Stammdaten `stellplatz_id`, `name` und `stellplatz_typ`. Die aktuelle Wohnungsbeziehung wird in `stellplatz_zuordnung` mit `stellplatz_id`, `wohnung_id` und `miete` geführt.

Ein Datenbank-Unique-Constraint stellt sicher, dass ein Stellplatz höchstens einer Wohnung zugeordnet ist. Die Umstellung erfolgt über eine neue Django-Migration: Sie überträgt vorhandene Werte zuerst in die Zuordnungstabelle und entfernt anschließend die alten Spalten. `bewerbung_stellplatz` referenziert weiter direkt den Stellplatzstamm.

## Konsequenzen

- Eine Wohnung kann null bis mehrere Stellplätze haben; ein Stellplatz kann unzugeordnet bleiben.
- Der Mietbetrag wird ausschließlich an der aktuellen Zuordnung gepflegt.
- Stellplatzstammdaten, Wohnungszuordnung und Miete werden ausschließlich in der Stellplatzverwaltung gepflegt; das Wohnungsformular enthält keine Stellplatzfelder.
- Bestehende Stellplatzdaten bleiben bei der Migration erhalten.
- Eine zeitliche Vermietungshistorie oder Vertragsdaten werden nicht eingeführt.
