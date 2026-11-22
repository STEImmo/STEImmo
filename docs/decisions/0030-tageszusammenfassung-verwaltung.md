# Tageszusammenfassung für offene Verwaltungsaufgaben

Das Dashboard und die dokumentierten Vorgangsereignisse bestimmen Aufgabe und
Wartebeginn. Eine Zusage allein erfordert keine Neuplanung. Vertragsrückläufe
folgen, sobald der Ablauf sie dokumentiert.

Der gemeinsame Befehl `remind_open_steps` zeigt beide Erinnerungsarten in der
Vorschau. Mit `--send` läuft die Verwaltungsauswertung von Montag bis Freitag
ab 09:00 Uhr in Europe/Berlin ohne Feiertagskalender. Reguläre Aufgaben müssen
zum Tagesfenster bereits zwei Werktage zur gleichen Ortszeit offen sein.
Termingebundene Aufgaben werden spätestens am letzten Werktag vor dem Termin
berücksichtigt und laufen mit dem Termin ab. Betriebsaufruf und Versandfreigabe
gehören zu #194. Demo bleibt versandfrei.

Aktive Konten mit Verwaltungszugriff, E-Mail-Adresse und aktiver Auswahl für die
Tageszusammenfassung sind berechtigt. Erfolgreiche Sofortmeldungen seit 09:00 Uhr
entfernen dieselbe Aufgabenversion für denselben Empfänger aus der Tagesmail.

Die vorhandene Versandhistorie erzwingt eine Versandabsicht pro Empfänger und
lokalem Kalendertag. Sie speichert die vorgemerkte Aufgabenauswahl. Versand und
Statusübergänge nutzen die Anwendungssperren der Einzelmeldungen. Entfallene
Einträge bleiben auch bei einer Wiederholung entfernt. Vorübergehende
SMTP-Ablehnungen können im selben Versandtag erneut verarbeitet werden.
