# ADR 0024 · Globale Einstellungen

## Entscheidung

Der Verwaltungsbereich setzt Mitarbeiterzugang und das Recht
`immobilien.manage_global_settings` voraus. Benutzerverwalter können die Gruppe
**Einstellungsverwaltung** über die vorhandene Kontenverwaltung ausdrücklich zuweisen.
Die Gruppe enthält beide Rechte. Bestehende Gruppen erhalten das Einstellungsrecht nicht
automatisch. Für die Anmeldung gilt die bestehende Mitarbeiterprüfung.

Die Datenbank erlaubt höchstens einen globalen Einstellungsdatensatz mit ID 1. Solange noch
kein Datensatz gespeichert wurde, gilt der Modellstandard. Der Schalter für optionale
Nutzer-E-Mails startet aktiviert. Seine Versandanbindung erfolgt im Rahmen von #205 und
#200. Mailadressen und Testversand gehören zu #188, Organisationsdaten zu #192.

Beim Speichern wird der globale Datensatz gesperrt und seine Version mit der Formularversion
verglichen. Bei einem Konflikt wird der aktuelle Wert zur Prüfung angezeigt. Eine wirksame
Änderung erhöht die Version. Änderung und Protokolleintrag werden gemeinsam gespeichert.
Der Eintrag enthält Konto-ID, Zeitpunkt und Feldnamen. Die Konto-ID bleibt auch nach
Löschung des Kontos erhalten. Unveränderte Werte erzeugen keinen Protokolleintrag.
