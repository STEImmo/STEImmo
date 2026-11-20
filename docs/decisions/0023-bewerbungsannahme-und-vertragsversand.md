# ADR-0023 Bewerbungsannahme und Vertragsversand

- Status: Angenommen
- Datum: 2026-11-18
- Issue: [#180](https://github.com/STEImmo/STEImmo/issues/180)

## Entscheidung

Mitarbeitende können eine offene, eingereichte und aktive Hauptbewerbung in ihrer
Detailansicht annehmen. Der Zeitstempel `accepted_at` und ein Eintrag im
Änderungsverlauf werden zusammen gespeichert. Wiederholte Annahme behält den
ursprünglichen Zeitpunkt und Akteur. Bewerbungsstatus und Nachweiszugriff
behalten ihre bisherige Bedeutung. Ein späterer Rückzug beendet die
Versandberechtigung. Wohnungsstatus und Kontozuordnung gehören zum
Vermietungsabschluss in #181 und #182.

Der Versand ist eine eigene Aktion. Sie nimmt ein unverschlüsseltes PDF mit
höchstens 5 MiB entgegen. Die Detailansicht zeigt die hinterlegte Adresse der
Person aus der Bewerbung an. Eine serverseitige Signatur bindet Bewerbung,
zugeordnete Person und exakt angezeigte Adresse an das Formular. Nach der
PDF-Prüfung liest der Server den Bewerbungsstand und die Adresse erneut.
Bei abweichender Zuordnung oder Adresse wird nichts versendet; HTTP 409 zeigt
die aktuelle Adresse und ein frisches Formular zur erneuten Bestätigung.
Das PDF muss nochmals ausgewählt werden. Fehlende oder manipulierte Signaturen
werden als ungültiges Formular abgewiesen. Vergleich und Versand verwenden
denselben einmal ermittelten Adresswert. Dafür ist keine SMTP-Datenbanksperre
und keine neue Migration erforderlich. Ergänzt nach Review zu PR #198 am 20.11.2026.
Das PDF wird als Anhang über das konfigurierte Django-Mail-
Backend versendet. Konsolen-, Datei- und Dummy-Backends werden für Verträge
abgewiesen, damit sie weder in Logs noch in lokalen E-Mail-Dateien landen.
In der Anwendung bleiben Zeitpunkt, Akteur und Ergebnis im
Änderungsverlauf erhalten. Das PDF wird für diesen Vorgang nur für den Upload
und Versand verarbeitet.

SMTP läuft außerhalb einer Datenbanktransaktion. Die Anwendung prüft den
Bewerbungsstand nach der PDF-Prüfung erneut. Vor dem Versand werden außerdem
das aktive Mitarbeiterkonto, dessen aktuelle Rechte, unveränderte Zugangsdaten
und die weiterhin gültige Datenbanksitzung erneut geprüft. Ein während der
Dateiprüfung erfolgter Widerruf beendet den Versuch mit HTTP 403 ohne Mailversand.
Das Ergebnis beschreibt die
Übergabe an das Mail-Backend, eine Bestätigung der Zustellung gibt es dabei
nicht. Nach einem Fehler kann ein Mitarbeiter die Datei erneut zum Versand
auswählen. Jeder ausdrücklich ausgelöste Versand ist ein eigener Versuch.
