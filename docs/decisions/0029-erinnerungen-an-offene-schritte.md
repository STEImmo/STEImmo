# Erinnerungen an offene Schritte

Hauptbewerbungen werden 48 Stunden nach der dokumentierten Freischaltung
erinnerungsfähig. Bei einer unbeantworteten Besichtigung gilt als
Mindestvorlauf für die verbindliche Einladung 48 Stunden. Der Versand ist
im Zeitfenster 25 bis 24 Stunden vor Beginn zulässig, damit ein regelmäßiger
Aufruf die Grenze von 24 Stunden einhalten kann. Der Aufruftakt muss beim
Rollout kürzer als dieses Fenster gewählt werden. Bei einer Verschiebung
zählt das Ereignis der neuen Terminvorgabe. Datenkorrekturen und erneutes
Senden einer Einladung ändern den Startzeitpunkt der Wartephase nicht.
Die Zeitregeln ändern keine fachliche Frist oder den Bewerbungsstatus.

Versand und Wiederholung verwenden den bestehenden Benachrichtigungsverlauf.
Die Ereignis-ID begrenzt die Erinnerung je Aufgabe auf eine Empfängerzuordnung.
Die aktuell zugeordnete Person benötigt Bewerberzugriff und die Mailart muss
gemäß #205 aktiv sein. Eine Änderung der persönlichen Auswahl nach Fälligkeit
holt eine bereits fällige Erinnerung nicht nach. Bei globaler Wiederfreigabe
gilt dasselbe für die betroffene Mailart, auch ohne vorherigen Erinnerungslauf.
Der vorhandene Einstellungsverlauf liefert den Zeitpunkt der Wiederfreigabe.
Ohne historisches
Freischalt- oder Terminereignis fehlt ein belastbarer Beginn der Wartephase.

`python manage.py remind_open_steps` zeigt eine Vorschau ohne Änderungen.
`--send` verarbeitet fällige Erinnerungen und vorgemerkte Wiederholungen.
Der Befehl benötigt eine öffentliche Anwendungsadresse für geschützte Links.
Demo und lokale Ausgabe-Backends bleiben versandfrei. Der regelmäßige
Aufruf und die Versandfreigabe folgen separat in #194. Vertragsrückläufe
bleiben bis zur fachlichen Freigabe nach #180/#181 deaktiviert.
