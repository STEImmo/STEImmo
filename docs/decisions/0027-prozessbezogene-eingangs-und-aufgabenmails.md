# ADR 0027 · Eingangsbestätigungen und Verwaltungsaufgaben

Datum: 21.11.2026 · Bezug: #201, #200, #205, #148 und #139

## Entscheidung

Verbindlich gespeicherte Besichtigungsanfragen und Hauptbewerbungen erzeugen in
derselben fachlichen Transaktion je eine Eingangsbestätigung für das eigene Konto
und einen Prüfungshinweis je berechtigtem Verwaltungskonto. Automatisch wegen der
Belegungsgrenze abgelehnte Anfragen erzeugen keine irreführende Wartebestätigung.
Entwürfe, Uploads, ungültige Eingaben, interne Prioritäten und Rollbacks erzeugen
keine solchen Absichten. Derselbe eingereichte Stand wird nicht erneut versendet.

Terminantworten verwenden das vorhandene Terminereignis und seine Version. Zusagen
melden „Terminzusage berücksichtigen“, Absagen und zurückgezogene Zusagen die
gegebenenfalls nötige neue Planung. Die Bewerbung bleibt aktiv. Der handelnde
Bewerber erhält keine weitere Antwortbestätigung. Alternativvorschläge behalten
genau ihren bestehenden Versandweg aus #148.

Ein dokumentierter Vertragsrücklauf existiert im aktuellen Modell nicht. Annahme,
Vertragsversand, Download und Vermietungsabschluss gelten nicht als Rücklauf. Es
wird dafür kein Ereignis und kein neuer Vertragsworkflow erzeugt.

## Empfänger und Einstellungen

Die eine Immobilie hat keine individuelle Verwaltungszuordnung. Empfänger sind
aktive Konten mit `immobilien.access_employee_area`, einschließlich direkter
Einzelrechte und Superuser. Dieselbe Berechtigung schützt alle Bewerbungsdetails.
Rückrufempfänger sind kein Bewerbungsverteiler. Jede Person erhält eine eigene
Mail; persönliche Abwahl leitet nichts an andere Konten um.

Nutzer-Empfänger benötigen die Bewerberberechtigung und die weiterhin passende
Person-Konto-Zuordnung. Die aktuelle Kontoadresse ist gemäß #205 maßgeblich. Rollen,
Aktivität, Objektzugang, Vorgangsstand und Auswahl werden bei jedem Versuch und
nochmals nach der Versandreservierung geprüft. Nachrichten enthalten Anlass,
nächsten Schritt und geschützten Link, keine Nachweise, internen Bewertungen,
Freitexte oder Anhänge. Eingänge sind keine Zusage und nennen keine erfundene Frist.
Absagen behalten den Bewerberlink aus der Einladung, niemals den Verwaltungslink
einer zwischenzeitlichen Terminantwort.

Der auf main integrierte Katalog und `mail_allowed` aus #205 / ADR 0026 werden
unverändert wiederverwendet: Bewerbungseingänge gehören zu `application_receipts`,
Verwaltungseingänge zu `new_applications`, Antworten und Alternativvorschläge zu
`viewing_responses`. Terminmails bleiben `viewing_changes` zugeordnet. Die
vorhandenen Konto- und Administrationsformulare werden verwendet; es gibt keine
zweite Einstellungsverwaltung und keinen zweiten Präferenzdatensatz.

Die widersprüchliche Vorrangtabelle in #205 wurde ausdrücklich gemäß #200 geklärt:
Persönliches An benötigt weiterhin die Admin-Freigabe der konkreten Nutzer-Mailart.
Dies entspricht auch der inzwischen integrierten Entscheidung in ADR 0026.
Persönliches Aus unterdrückt immer. Verwaltungsmails verwenden ihre eigenen Gruppen.
Abschalten markiert ausstehende und eindeutig fehlgeschlagene Absichten dauerhaft
als unterdrückt. Erneutes Anschalten erzeugt keinen Nachversand. Pflichtcodes,
Rückrufzustellung und ausdrücklicher Vertragsversand behalten ihre eigenen Wege.

## Versand und Parallelität

`ProcessNotification` ergänzt die bestehenden Ereignisse um eine eindeutig
beschränkte Absicht je Bewerbung, Ereignis und Empfängerkonto. Gespeichert werden
Art/Kennung, optional das Terminereignis, Link, Zeitpunkte, Status und Versuchszahl.
Die Empfängermenge wird beim Ereignis festgelegt und nicht bei einem Retry erweitert.
Der bestehende Terminstatus und `recipient_results` werden weitergeführt; bei der
Übernahme älterer offener Terminereignisse bleiben erfolgreiche und unterdrückte
Empfänger terminal.

Erst nach dem Commit wird die bestehende Django-Mailmechanik mit Reply-To benutzt.
Pro Bewerbung teilen Versand und relevante fachliche Änderungen eine
PostgreSQL-Advisory-Sperre. Änderungen nehmen sie vor der Bewerbungszeilensperre,
gegebenenfalls nach der Wohnungszeilensperre. Der Versand nimmt eine Sitzungssperre,
prüft und reserviert die Absicht in einer kurzen Transaktion und beendet diese vor
dem SMTP-Aufruf. Personen-/Kontodaten werden erst nach dem kurzen Bewerbungssperren-
Warten neu gelesen. Während SMTP bestehen keine offenen Versandtransaktionen oder
Zeilensperren dieses Versandwegs. Die Sitzungssperre wird auch bei Fehlern freigegeben.

Eine zuvor festgeschriebene Absage oder Änderung kann deshalb nicht von einer alten
gültigen Einladung überholt werden. Später beginnende Änderungen warten bis zum
Ende dieses begrenzten Versandversuchs. Der bestehende SMTP-Timeout gilt weiterhin.
Es gibt keine neue Queue-Plattform und keinen Dienst. Die Sperre kann weiterhin
eine einzelne Bewerbungsänderung kurz verzögern; der Schutz vor veralteten Terminen
wird nicht ersatzlos entfernt. Der separate bestehende Main-Einladungsversand wird
fachlich nicht umgebaut.

`pending` und eindeutig nicht übergebene `failed` erlauben höchstens drei Versuche.
Verbindungsablehnung oder ausdrückliche SMTP-Ablehnung erlauben Retry. Timeouts und
sonstige unklare Ergebnisse werden `uncertain` und nicht automatisch wiederholt.
Nach Prozessabbruch verbliebene `sending`-Reservierungen werden ebenfalls nicht
blind wiederholt. Erfolgreiche, unterdrückte und überholte Absichten sind terminal.
Externe Zustellung genau einmal wird nicht behauptet. Fehlerausgaben sind bereinigt;
die Verwaltungsdetailseite zeigt Status und Versuchszahl. SMTP-Fehler rollen einen
erfolgreichen fachlichen Vorgang nicht zurück.

`python manage.py retry_process_notifications` verarbeitet höchstens 100 offene
Absichten je Aufruf unter erneuter Prüfung. Das Kommando erzeugt keine historischen
Einreichungsereignisse. Bestehende offene Terminereignisse können beim expliziten
Wiederholungsaufruf übernommen werden. Ein betrieblicher Zeitgeber bleibt #194;
diese Änderung aktiviert keinen produktiven Versand und kein Deployment. Im Demo-
Modus wird zusätzlich zum vorhandenen Dummy-Backend vor dem Transport unterdrückt.

## Bestehende Statusanzeigen

Der nächste Schritt bleibt aus Bewerbung, Einreichung, Annahme, Vermietungsabschluss
und aktuellem Termin abgeleitet. Nach Einreichung prüft die Verwaltung; nach
Freischaltung ist die Hauptbewerbung eine Nutzeraufgabe. Terminabsagen weisen auf
weitere Planung, Zusagen auf Berücksichtigung des Termins hin. Verwaltungsdetails
verwenden die vorhandene Dashboard-Ableitung für Prüfung, Planung und Warten auf
Hauptbewerbung. Es gibt keine zweite Aufgabenverwaltung.
