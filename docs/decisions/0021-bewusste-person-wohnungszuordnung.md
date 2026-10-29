# ADR-0021: Bewusste Person-Wohnungszuordnung

- Status: Angenommen
- Datum: 2026-10-29
- Issue: [#168](https://github.com/STEImmo/STEImmo/issues/168)

## Kontext

Einzugsprotokolle erlauben ausschließlich Personen der ausgewählten Wohnung.
Die bestehende Beziehung `Person.wohnung` war nicht über die Verwaltung pflegbar.

## Entscheidung

Mitarbeiter verwalten die Zuordnung über eine eigene UIkit-Maske an der Wohnung.
Die Personenauswahl zeigt zunächst aktuelle Wohnung, Konto, Rollen und Protokolle.
Erst ein bestätigter POST setzt die Zuordnung; Bewerbungen, Wohnungsstatus und
Kontorollen ändern sich dabei nicht. Die vorhandene Benutzerverwaltung bleibt
für Kontoverknüpfung und die zusätzliche Vergabe der Mieterrolle zuständig.
Der Hinweis fordert ausdrücklich den Erhalt der Bewerberrolle.

Ein Wechsel ersetzt nur `Person.wohnung`. Er ist bei offenen oder gesperrten
Protokollen der Person blockiert, bis diese fachlich geklärt und abgeschlossen sind.
Bestätigte Protokolle behalten Person, Wohnung und Inhalte. Die Person wird beim
Speichern gesperrt und ihre bisherige Zuordnung erneut geprüft, damit konkurrierende
Zuordnungsänderungen nicht unbemerkt überschrieben werden.

## Konsequenzen

Keine Migration oder weitere Technologie ist erforderlich. Es gibt keine
automatische Vermietungsentscheidung und keine neue Kontoverknüpfungslogik.
Fehlende Beteiligte im Übergabeformular führen direkt zur Zuordnungspflege.
Eine Entfernung der Zuordnung ohne neue Zielwohnung ist nicht Teil dieses Ablaufs.
