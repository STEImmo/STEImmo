# ADR 0025 · Fachliche Mailadressen

## Entscheidung

Die globalen Einstellungen aus #186 speichern Rückrufempfänger und eine optionale Antwortadresse. Der Standardabsender und die SMTP-Verbindung kommen weiterhin aus der Betriebskonfiguration. Reply-To gilt für Rückrufwünsche, Besichtigungseinladungen, Einladungen zur Hauptbewerbung und Testmails.

Ein fehlender Datenbankwert für Rückrufempfänger bedeutet, dass die bisherige Variable `DJANGO_CALLBACK_RECIPIENTS` gilt. Mit der ersten gültigen Speicherung übernimmt die Datenbank die Empfängerliste. Sobald die gespeicherte Liste geprüft ist, kann der Betrieb die Altvariable aus der Umgebung entfernen. Die Migration übernimmt keine umgebungsspezifischen Adressen.

Testversuche werden pro Konto vor dem Versand für eine Minute begrenzt. Der separate POST verwendet die gespeicherten Einstellungen und die Kontoadresse. In der Demo endet die Aktion vor dem Zugriff auf das Mail-Backend.
