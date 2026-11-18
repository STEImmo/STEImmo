# ADR-0025 Zugriff auf Systemeinstellungen

- Status: Angenommen
- Datum: 2026-11-18
- Issue: [#185](https://github.com/STEImmo/STEImmo/issues/185)

## Entscheidung

Das Einzelrecht `immobilien.manage_system_settings` wird ausdrücklich einem
Konto zugewiesen. Die bestehenden Gruppen und der Django-Superuserstatus
vergeben es nicht automatisch. Der Betrieb vergibt das erste Recht mit
`python manage.py grant_system_settings_access <Anmeldename>` an ein bestehendes
funktionsfähiges Konto. Auf der geschützten Seite können berechtigte Konten das
Recht weiteren Konten erteilen und vorhandene Rechte entziehen.

Der Bereich verwendet das bestehende Passwort-Login mit E-Mail-Einmalcode.
Der erfolgreiche Code bestätigt die Sitzung für dieses Konto. Jede Seite und
Aktion prüft Einzelrecht und bestätigte Sitzung. Vergabe und Entzug laufen
über CSRF-geschützte POST-Anfragen und widerrufen bestehende Sitzungen und
ausstehende Anmeldecodes des betroffenen Kontos.

Die normale Benutzerverwaltung kann das Einzelrecht nicht vergeben und
geschützte Konten nicht bearbeiten. So kann sie weder über Passwortreset noch
über die Änderung der Personenzuordnung auf Systemeinstellungen zugreifen.
Die reguläre eigene Profilpflege mit Passwort- und E-Mail-Bestätigung bleibt
verfügbar.

Änderungen verwenden dieselbe Datenbanksperre wie die Benutzerverwaltung und
prüfen die Berechtigung sowie die Sitzung des handelnden Kontos unmittelbar
vor dem Schreiben erneut. Ein Entzug muss mindestens ein funktionsfähiges
berechtigtes Konto erhalten. Dafür zählen aktive Konten mit verwendbarem
Passwort und gültiger E-Mail-Adresse. Die tatsächliche Mailzustellung ist eine
Betriebsvoraussetzung.

Dieser Schritt stellt den Zugriffsschutz bereit. Die Konfigurationsansicht
und SMTP-Einstellungen folgen in den zugehörigen Stories des Epics #184.
