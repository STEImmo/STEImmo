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
Person aus der Bewerbung an. Der Server liest die Adresse beim Versand erneut
aus der Bewerbung. Das PDF wird als Anhang über das konfigurierte Django-Mail-
Backend versendet. Konsolen-, Datei- und Dummy-Backends werden für Verträge
abgewiesen, damit sie weder in Logs noch in lokalen E-Mail-Dateien landen.
In der Anwendung bleiben Zeitpunkt, Akteur und Ergebnis im
Änderungsverlauf erhalten. Das PDF wird für diesen Vorgang nur für den Upload
und Versand verarbeitet.

SMTP läuft außerhalb einer Datenbanktransaktion. Die Anwendung prüft den
Bewerbungsstand nach der PDF-Prüfung erneut. Das Ergebnis beschreibt die
Übergabe an das Mail-Backend, eine Bestätigung der Zustellung gibt es dabei
nicht. Nach einem Fehler kann ein Mitarbeiter die Datei erneut zum Versand
auswählen. Jeder ausdrücklich ausgelöste Versand ist ein eigener Versuch.
