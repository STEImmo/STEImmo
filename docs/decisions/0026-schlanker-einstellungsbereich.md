# ADR-0026 Schlanker Einstellungsbereich

- Status: Angenommen
- Datum: 2026-11-19
- Issue: [#186](https://github.com/STEImmo/STEImmo/issues/186), Zugriffsschutz aus #185
- Ergänzt ADR-0025 nach der Zusammenführung der Einstellungs-Stories.

## Umfang und Rechte

Der Bereich bietet die gemeinsame Grundlage für Mailadressen/Testversand (#188),
Organisationsdaten (#192) und die globale Freigabe optionaler Nutzer-Mails (#205).
Die beiden fachlichen Formulare bleiben eigene Stories; der Einstieg kennzeichnet
sie bis zur Umsetzung ausdrücklich als noch nicht verfügbar. Betriebswerte und
allgemeine Systemstatusanzeigen gehören nicht hierher. Persönliche Präferenzen
werden in #205 separat im eigenen Konto umgesetzt.

Das direkte Recht und die bestehende Mailcode-Anmeldung aus ADR-0025 bleiben
verbindlich. Die Vergabe/Entziehung findet nun in der vorhandenen Benutzerverwaltung
statt. Dafür sind sowohl Benutzerverwaltungsrecht als auch ausdrücklicher
Systemeinstellungszugriff und Mailcode-Bestätigung erforderlich. Ein reiner
Einstellungsverwalter kann globale Vorgaben pflegen, aber keine fremden Konten
verwalten. Der Betriebsbefehl ermöglicht die Erstvergabe. Geschützte Konten bleiben
gegen Übernahme durch gewöhnliche Benutzerverwalter abgesichert.

## Speicherung und gleichzeitige Änderungen

`SystemSettings` enthält genau einen durch Datenbank-Constraint abgesicherten
Datensatz mit Version und zunächst aktivierter globaler Nutzer-Mailfreigabe.
Neue Migrationen ergänzen das Schema; die bereits geteilte Migration 0035 bleibt
unverändert. Formularversion und Datenbanksperren verhindern, dass ein veralteter
Tab neuere Werte oder Rechte unbemerkt überschreibt. Ein Konflikt antwortet mit
HTTP 409 und verlangt Neuladen und erneute Prüfung. Ungültige Formulare ändern
keine Werte. Rechte und bestätigte Datenbanksitzung werden vor dem Schreiben
erneut geprüft. Kontoverwaltung und Einstellungsänderungen verwenden dieselbe
Sperrreihenfolge.

Erfolgreiche Änderungen erzeugen in derselben Transaktion einen
`SystemSettingsChange` mit Konto, Zeitpunkt, fest benannten Feldern und Aktion.
Feldinhalte und Geheimnisse werden nicht gespeichert. Der Betriebsbefehl wird
ohne Webkonto erfasst. Die Oberfläche zeigt die letzten 30 Einträge; sie ist
kein vollständiges Infrastruktur-Audit. Unverändertes Speichern erzeugt keinen
Änderungseintrag. Konten werden regulär deaktiviert; die Historie bleibt erhalten.

## Globale Nutzer-Mailfreigabe

Die Freigabe wird unabhängig von Konten und persönlichen Kategorien gespeichert.
Sie verändert keine persönliche Auswahl und keine fachlichen Vorgänge. #205
muss diese globale Bedingung zusätzlich zur persönlichen Kategorie und aktuellen
Vorgangsberechtigung vor jedem optionalen Nutzerversand berücksichtigen.

Die bereits vorhandenen Terminmails an Bewerber und Einladungsmails zur
Hauptbewerbung beachten den aktuellen Wert. Unterdrückung hat einen eigenen
Status und gilt weder als SMTP-Fehler noch als Versand. Beim Abschalten werden
wartende/fehlgeschlagene Terminmails sowie noch ausstehende fehlgeschlagene
Main-Einladungen unterdrückt. Nach Wiedereinschalten werden diese alten Ereignisse
auch über Retry nicht nachgesendet; neue zulässige Anlässe bleiben möglich.
Eine Freischaltung der Hauptbewerbung bleibt trotz unterdrückter Mail bestehen.

Verwaltungsnachrichten (z.B. Alternativtermine), Sicherheits-/Kontobestätigungscodes,
Rückrufrouting und der ausdrücklich ausgelöste Vertragsversand aus #180 bleiben
unabhängig. Bei mehreren Rollen entscheidet der konkrete Mailzweck. Es entsteht
kein neuer Mailversand und keine neue SMTP-Konfiguration. Die bestehende
SMTP-/Transaktionskopplung wird weiterhin separat in #139/#189 behandelt.
