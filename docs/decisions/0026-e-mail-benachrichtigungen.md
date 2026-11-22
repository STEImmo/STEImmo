# ADR 0026 · E-Mail-Benachrichtigungen

Die persönlichen Benachrichtigungen aus [#205](https://github.com/STEImmo/STEImmo/issues/205)
werden pro Konto und fachlicher Gruppe gespeichert. Bewerber und Mieter können den
Verwaltungsstandard übernehmen oder ausdrücklich An beziehungsweise Aus wählen.
Persönliches An und der Verwaltungsstandard erlauben nur eine administrativ freigegebene
Mailart. Persönliches Aus unterdrückt die gesamte Gruppe. Verwaltungsmails sind standardmäßig
aktiviert und folgen unabhängig davon der persönlichen Verwaltungsgruppe.

Die Freigaben liegen je Mailart im vorhandenen globalen Einstellungsdatensatz aus ADR 0024.
Die Migration überträgt einen gespeicherten Gesamtschalter auf alle bisherigen Mailarten.
Fehlende Freigaben starten aktiviert. Das ist eine Produktvoreinstellung. Gesperrte Kategorien
bleiben bei einem Rollenwechsel gespeichert. Die Formulare prüfen eine Version und das
globale Änderungsprotokoll nennt jede tatsächlich geänderte Mailart.

Die Versandwege prüfen zuerst den aktuellen Anlass und die fachliche Zugriffsberechtigung.
Danach prüfen sie unmittelbar vor jedem Zustellversuch die aktuellen Einstellungen. Bei
Terminbenachrichtigungen speichert das bestehende Ereignis den Zustand pro Empfängerkonto.
Nur fehlgeschlagene Empfänger werden erneut geprüft. Unterdrückte Ereignisse werden nach
erneuter Freigabe nicht nachgesendet. Die Hauptbewerbung verwendet ihren bestehenden
Ereignisverlauf für Versand, Fehler und Unterdrückung.

Sicherheitscodes, Rückrufrouting und ausdrücklich ausgelöste Vertragszustellung behalten
ihre eigenen Versandwege. Neue optionale Versandwege aus #201–#204 verwenden denselben
Katalog und dieselbe Einstellungsprüfung.

## Sicherheitscodes bei Mailstörungen (Issue #189)

Registrierung und Mitarbeiteranmeldung verwenden die vorhandene Fehlerbehandlung:
SMTP- und Verbindungsfehler sowie null zugestellte Nachrichten gelten als
fehlgeschlagener Versand. Es gibt keine erfolgreiche Anmelde- oder Versandbestätigung
für diesen Fall. Das unbestätigte Registrierungskonto bleibt mit seiner Wartezeit
erhalten. Eine erneute Codeanforderung ist frühestens eine Minute nach dem letzten
Versandversuch möglich und ersetzt den alten Code, auch wenn der neue Versand
scheitert. Ablaufzeit von 15 Minuten und fünf Bestätigungsversuche bleiben bestehen.
Beim fehlgeschlagenen MFA-Versand werden nur der betroffene Code und der ausstehende
Anmeldeversuch verworfen; ein inzwischen neuerer Code bleibt erhalten. Die Anmeldung
kann mit Passwort erneut begonnen werden, ohne die Pflicht zur MFA aufzuheben.

Die öffentliche erneute Codeanforderung verwendet für unbekannte und aktive Konten,
Versuche innerhalb der Wartezeit und offene Registrierungen dieselbe Textmeldung,
Weiterleitung und Informationsstufe. Auch ein tatsächlicher Versandfehler verändert
diese Antwort nicht. Die Informationsstufe vermeidet eine grüne Erfolgsmeldung, ohne
Kontenexistenz oder Versandresultat offenzulegen. Dies ist keine Zusicherung gleicher
Antwortzeiten. Bei der erstmaligen Registrierung und nach erfolgreicher Passwortprüfung
darf der betroffene Ablauf den fehlgeschlagenen Versand ausdrücklich erklären.

Warnungen unter `core.views` nennen nur den festen Ablauf `registration`,
`registration_resend`, `employee_mfa` oder beim bestehenden E-Mail-Wechsel
`email_change` und die Fehlerklasse beziehungsweise
`no delivery`. Empfänger, Codes, Passwörter, Mailinhalte, SMTP-Fehlertexte und
Tracebacks werden nicht übernommen. Nach einer Störung prüft der Betrieb die
geschützte Serverkonfiguration für SMTP-Host, Port, TLS, Authentifizierung,
Absenderberechtigung und Timeout gemäß README und #194. Nach Behebung fordert der
Nutzer innerhalb der bestehenden Grenzen einen neuen Code an beziehungsweise beginnt
die Mitarbeiteranmeldung erneut. Es gibt keine neue Einstellungsseite, automatische
Retry-Schleife oder MFA-Abschaltung. Das Demo-Profil verwendet weiterhin ausschließlich
den Dummy-Mailbackend; diese Änderung richtet keinen Produktivversand ein.
