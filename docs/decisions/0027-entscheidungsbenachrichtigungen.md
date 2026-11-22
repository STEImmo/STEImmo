# 0027 Entscheidungs- und Abschlussbenachrichtigungen

Optionale Hinweise für #202 greifen bestehende fachliche Übergänge und die
Versandentscheidung aus #205 auf. Die Annahme und der ausdrückliche Vertragsversand
sind getrennte Aktionen. Sobald der Vertragsversand protokolliert wurde, wird eine
noch wartende Annahmemail unterdrückt. Die Vertragsmail nennt die Annahme und den
nächsten Schritt. Rückzüge informieren aktive Konten mit Mitarbeiterzugriff, weil
der vorhandene Bewerbungsablauf keine personenbezogene Bearbeitungszuordnung hat.
Terminbezogene offene Schritte werden über die bestehende Absage beendet. Künftige
Erinnerungsläufe aus #203 berücksichtigen den aktuellen fachlichen Zustand.

Die Versandabsicht wird innerhalb der fachlichen Transaktion pro Ereignisversion
und Konto eindeutig gespeichert. Nach dem Commit sowie bei
`python manage.py send_decision_notifications` wird der Anlass einschließlich
Empfängerberechtigung, Dokumentverfügbarkeit und aktueller Präferenzen geprüft.
Eine Abwahl unterdrückt bereits vorgemerkte Meldungen zusammen mit dem Speichern
der Einstellungen dauerhaft. Nach der HTML-Erstellung wird der Anlass mit dem
aktuellen Konto erneut unmittelbar vor der SMTP-Übergabe geprüft.
Der Befehl kann durch den betrieblichen Zeitgeber aus #194 aufgerufen werden.
HTTP-Auslöser verwenden den geprüften Request-Host. Für modellseitige Auslöser ohne
HTTP-Request muss `DJANGO_DECISION_NOTIFICATION_ORIGIN` die öffentliche HTTPS-Adresse
des Projekts enthalten.

Maximal drei Zustellversuche sind bei einer vorübergehenden SMTP-Ablehnung oder
einer verweigerten Verbindung zulässig. Bei unklarem Transportergebnis oder
Prozessabbruch nach Beginn des Versands prüft der Betrieb den Versandstatus vor
einer erneuten Zustellung. Demo- und Vorschau-Mailbackends unterdrücken Hinweise.
Die Protokollmail prüft dieselbe archivierte PDF-Datei samt Prüfsumme wie der Download.
Die Vermietungsabschlussmeldung wird angebunden, sobald #183 den eigenen
geschützten Zugriff auf die Wohnungsunterlagen bereitstellt.
