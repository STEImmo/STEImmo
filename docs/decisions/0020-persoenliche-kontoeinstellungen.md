# ADR-0020: Persönliche Kontoeinstellungen

- Status: Angenommen auf ausdrücklichen Nutzerauftrag
- Datum: 2026-10-23
- Issue: #129 (US-21), auf Nutzerauftrag um Kontoeinstellungen erweitert

## Entscheidung

Der bestehende Profilbereich erhält die optionalen Angaben Anrede, Geburtsdatum
und Anschrift sowie getrennte Formulare für Passwort und Anmelde-E-Mail.
Anrede wird separat vom vorhandenen Geschlechtsfeld gespeichert; Geschlecht,
Titel, Rollen und Wohnungszuordnung bleiben unverändert. Das vorhandene
Geburtsdatum wird wiederverwendet. Die Anschrift liegt als Straße/Hausnummer,
Postleitzahl, Ort und Land direkt an Person, ohne zusätzliche Adressverwaltung.
Alle vier Adressfelder müssen gemeinsam gefüllt oder leer sein. Internationale
Postleitzahlen sind erlaubt. Ein natives Datumsfeld und serverseitige Prüfung
verhindern ein zukünftiges Geburtsdatum. Migration 0029 ergänzt ausschließlich
optionale Felder und eine Tabelle für ausstehende E-Mail-Änderungen.

### Zugriff und Passwortwechsel

Die eigene Person wird ausschließlich über das angemeldete Konto ermittelt.
Auch Profil-Leseanfragen und der Aufruf des Bearbeitungsformulars prüfen den
aktuellen Kontostand unter derselben User-Zeilensperre wie Anmeldung und Verwaltung.
Danach wird die Person gesperrt. Geänderte Zugangsdaten, Deaktivierung und eine
administrative Neuzuordnung können keine veraltete Anfrage weiterberechtigen.
Die Datenbanksitzung muss unter der Kontosperre weiterhin bestehen; ein
administrativer Sitzungswiderruf gilt damit auch bei unveränderten Zugangsdaten
für bereits laufende Profilanfragen.

Der Passwortwechsel verwendet Djangos PasswordChangeForm und vorhandene
Passwortvalidatoren. Das aktuelle Passwort ist erforderlich; sein Vergleich
aktualisiert während der Formularvalidierung keinen Passwort-Hash. Die vorhandenen
Konto-/IP-Versuchsgrenzen gelten auch für Passwortbestätigungen dieser Formulare.
Passwort, E-Mail und Stammdaten werden nie aus beliebigen POST-Feldern übernommen.
Alle schreibenden Ansichten verlangen POST und CSRF, alle Kontoansichten private
no-store-Antworten.

Ein erfolgreicher Passwortwechsel löscht sämtliche authentifizierten
Datenbanksitzungen dieses Kontos und offene Registrierungs-, MFA- und
E-Mail-Änderungscodes unter der Kontosperre. Die aktuelle Sitzung wird abgemeldet.
Die nächste Anmeldung läuft regulär, einschließlich gegebenenfalls erforderlicher
Mitarbeiter-MFA. Die kontobezogene Passwortfehlversuchsfolge wird zurückgesetzt;
die IP-Grenze bleibt bestehen. Es gibt keine dauerhafte Gerätefreigabe.

### E-Mail-Wechsel

Nach Bestätigung des aktuellen Passworts wird eine normalisierte neue Adresse
geprüft. Konten und Personen mit derselben Adresse werden unabhängig von
Groß-/Kleinschreibung berücksichtigt; die Adresse muss in das bestehende
User.username-Feld passen. Zunächst bleiben die bisherigen Zugangsdaten gültig.

PendingEmailChange enthält pro Konto genau einen Zielwert, einen gehashten
sechsstelligen Zufallscode, eine zufällige Challenge-Kennung, Ablaufzeit,
Fehlversuche und den letzten Anforderungszeitpunkt. Ein HMAC bindet den Vorgang an
den bisherigen Passwort-/Benutzernamen-/E-Mail-Stand. Der Code gilt 15 Minuten und
hat fünf Versuche. Ein neuer Code ist frühestens nach einer Minute möglich und
ersetzt den bisherigen Vorgang; dessen Challenge ist dann ebenfalls ungültig.
SMTP läuft außerhalb der Kontotransaktion. Versandfehler ändern keine Zugangsdaten
und heben die Wartezeit nicht auf. Keine Adresse oder Codes werden protokolliert.

Erst nach gültiger Bestätigung werden User.username, User.email und Person.email
atomar geändert. Unmittelbar davor werden Kontostand, Code, Frist, Versuchszahl,
Challenge und Adressverfügbarkeit erneut geprüft. Die Datenbank-Eindeutigkeit
sichert gleichzeitig bestätigte identische Zieladressen zusätzlich ab; eine
Kollision wird als Formularfehler behandelt und rollt sämtliche Schreibvorgänge
zurück. Wie bei bestehender Registrierung/Kontoverwaltung bleiben möglicherweise
bereits vorhandene mehrdeutige Alt-Konten durch die neutrale Anmeldeprüfung gesperrt.

Anschließend werden sämtliche alten Sitzungen und offenen Codes widerrufen und
eine erneute Anmeldung verlangt. Die Benutzerverwaltung verwirft ausstehende
E-Mail-Wechsel ebenfalls bei sicherheitsrelevanten Kontoänderungen. Andere Konten
können fremde Vorgänge weder bestätigen noch abbrechen. Ein ausdrückliches
Abbrechen löscht ausschließlich den eigenen ausstehenden Vorgang.

Im ausdrücklich aktivierten Demo-Profil gilt entsprechend ADR-0019 der sichtbare
Testcode 000000 auch für diesen Ablauf. Außerhalb des Demo-Profils sind Codes zufällig.
Es werden weder Mailbackend noch MFA-Verfahren abgeschwächt.

## Auswirkungen auf bestehende Daten

Die neuen Personenfelder sind anfangs leer. Es erfolgt keine automatische
Übernahme von Anschriften aus Protokollen und kein Überschreiben fachlicher
Bewerbungsdaten. Eingereichte Dateien und Texte sowie archivierte Protokolle,
Unterschriften und PDFs bleiben unverändert. Bestehende fachliche Ansichten dürfen
weiterhin aktuelle Stammdaten über Person darstellen.

Profilbearbeitung und Kontoeinstellungen gehören gemeinsam zu US-21 (#129)
und werden im Branch `feat/129-personal-profile` umgesetzt. Die Integration
erfolgt nach erfolgreicher CI, Review und freigegebenem Merge.
