# ADR-0025 Wohnungsstatus beim Vermietungsabschluss

- Status: Angenommen
- Datum: 2026-11-20
- Issue: [#182](https://github.com/STEImmo/STEImmo/issues/182)

## Kontext

Der Abschluss aus #181 speichert Vermietung, Mieterkonto und Vertrag gemeinsam.
Der Wohnungsstatus blieb dabei unverändert. Eine bereits vermietete Wohnung
konnte dadurch weiterhin in der öffentlichen Suche verfügbar sein.

## Entscheidung

Die fachliche Bewerbungsannahme und der Vertragsversand aus #180 ändern den
Wohnungsstatus weiterhin nicht. Erst der erfolgreiche Vermietungsabschluss
setzt den vorhandenen Status `WohnungStatus.TAKEN` (Vermietet).

Der Status wird zusammen mit Vermietung, Person-Wohnungszuordnung, endgültigem
Vertrag und Mieterrolle in der bestehenden Datenbanktransaktion gespeichert.
Die vorhandene Wohnungssperre serialisiert gleichzeitige Abschlussversuche.
Schlägt ein Speicherschritt fehl, wird auch der Status zurückgerollt.
Der Abschluss setzt sowohl verfügbare als auch gesperrte oder bereits als
vermietet geführte Wohnungen auf Vermietet; die bisherigen Voraussetzungen
für angenommene Bewerbungen und eindeutige Zuordnungen bleiben bestehen.

Ein wiederholter Abschluss bleibt ohne erneute Statusänderung. Er darf einen
später durch Stammdatenpflege oder Übergabe geänderten Status nicht zurücksetzen.
Bestehende Such-, Detail-, Gebäude-, Etagen- und Verwaltungsansichten verwenden
weiterhin das gespeicherte Statusfeld. Es gibt kein zusätzliches Statussystem.
Die Statuswechsel bei bestätigten Ein- und Auszügen bleiben bestehen.

Das Wohnungsverwaltungsformular übermittelt den beim Öffnen vorhandenen
Vermietungsabschluss als unverbindlichen Vergleichswert (leer ohne Abschluss).
Status und Vergleichswert werden in derselben Datenbankabfrage geladen, damit
ein Abschluss während des Ladens keinen alten Status als aktuell bestätigt.
Nach der Formularprüfung wird dieser Wert unter der Wohnungssperre mit dem
aktuellen Abschluss verglichen. Ein zwischenzeitlicher Abschluss verwirft die
gesamte Stammdatenänderung mit einem Hinweis und verlangt erneute Prüfung.
Auch bei Formularfehlern bleibt der ursprünglich angezeigte Vergleichswert
erhalten. Ein frisch geöffnetes Formular erlaubt weiterhin bewusste spätere
Statusänderungen. Der Vergleichswert ersetzt keine Zugriffsprüfung.

Es ist keine Schemaänderung erforderlich. Frühere Abschlüsse werden nicht
pauschal nachträglich auf Vermietet gesetzt, da deren Wohnung inzwischen einen
anderen fachlich gültigen Status haben kann. Eine Beendigung und Neuvermietung
ist weiterhin ein eigener, hier nicht eingeführter Ablauf.

## Prüfung

Django-Tests prüfen den tatsächlichen Annahmeweg ohne Statuswechsel, den Abschluss
aus allen bisherigen Wohnungsstatus, Zuordnung und Vertragsbestand bei erneuter
Ausführung, vollständigen Rollback bei Status- und Rollenfehlern sowie öffentliche
Verfügbarkeit und Verwaltungsfilter. Die bestehenden Abschlussprüfungen sichern
zusätzlich Fehlerfälle, Berechtigungen und gleichzeitige Ausführung ab; die
Übergabeprüfungen decken die bisherigen Ein- und Auszugsstatuswechsel ab.
Zusätzliche Regressionstests prüfen alte Verwaltungsformulare, einen Abschluss
während des Ladens und der Formularprüfung, erneute Anzeige nach Eingabefehlern
sowie eine bewusste Statusänderung mit einem frisch geöffneten Formular.

## Integration mit main

Die zusätzliche Migration `0037_merge_rental_completion_and_global_settings`
verbindet den Abschluss aus #181 mit den globalen Einstellungen aus #186.
Sie enthält keine Daten- oder Schemaoperationen; beide bereits geteilten
Migrationszweige bleiben unverändert. Migrationstests prüfen das Upgrade von
beiden Zweigständen und den Erhalt von Einstellungen, Änderungsverlauf,
Vertragsdatei, Mieterkonto, Wohnungszuordnung und Annahmezeitpunkt.
