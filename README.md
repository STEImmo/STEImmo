# STEImmo

STE Immobilien eGbR

STEImmo ist der interne Projektname. Der sichtbare Auftritt verwendet den
Firmennamen **STE Immobilien eGbR**. Header, mobile Navigation und Footer bauen
auf dem UIkit-Theme aus US-17 auf. Der gemeinsame Seitenrahmen liegt in
`templates/base.html`, Header und Footer in `templates/partials/`.

## Projektziel

STEImmo ist eine serverseitig gerenderte Webanwendung für die Verwaltung und Vermarktung einer Immobilie mit 25 Wohneinheiten.

Studierende können verfügbare Einheiten suchen, filtern, ansehen und sich darauf bewerben. Die Immobiliengesellschaft verwaltet die Einheiten sowie eingehende Anfragen und Bewerbungen.

## Filter in den Verwaltungslisten

Mitarbeiter können Wohnungen nach Verfügbarkeitsstatus und Etage, Stellplätze nach
Typ und Wohnungszuordnung sowie Prüfvorlagen nach ihren drei festen Merkmalen
eingrenzen. Auch die Übergabeprotokoll-Liste kann nach Wohnung, Übergabeart,
beteiligter Person und Bearbeitungsstand gefiltert werden. „Nicht zugeordnet“
bezeichnet einen Stellplatz ohne Wohnungszuordnung und ist keine zusätzliche
Vermietbarkeitszusage.

Die beschrifteten Filter im Tabellenkopf öffnen sich per Klick oder Tastatur;
auf Mobilgeräten stehen sie oberhalb der Liste. Auswahländerungen werden unmittelbar
ohne vollständiges Neuladen angewendet und mit der URL sowie Browser-Zurück/Vor
synchronisiert. Die Name-/E-Mail-Suche wird mit kurzer Verzögerung ausgeführt.
Aktive Filter lassen sich einzeln oder gemeinsam entfernen. Ungültige Angaben werden
angezeigt und nicht angewendet; andere gültige Filter bleiben wirksam. Leere
Trefferlisten behalten ihre Filterbedienung.

Bei Bewerbungen gelten die Filter innerhalb der gewählten Wohnung und Ansicht
(„Passend“, „Einzelfallprüfung“, „Alle Bewerbungen“). Die Personenanzahl sucht nach
der exakten Haushaltsgröße. Beim Seitenwechsel bleiben Filter erhalten; eine neue
Auswahl beginnt auf Seite 1. Das Zurücksetzen erhält Wohnung, Ansicht und Sortierung.
Die Wohnungs-Auswahlliste lässt sich nach Etage und Zimmeranzahl filtern sowie nach
der Bewerbungsanzahl sortieren. Bei Übergabeprotokollen bleiben gespeicherte Entwürfe
vom Listenfilter getrennt.
Filteraufrufe verändern keine Bewerbungsstatus oder Wohnungsanforderungen.

## Projektstatus

Die [Startseite](http://localhost:8000/) verwendet das gewählte Unternehmensdesign
mit einer echten Würzburg-Luftaufnahme, Wohnungssuche, Gebäudevorschau, aktuellen
Bestandszahlen, großen Etagenlinks und Zugang zu den persönlichen Bereichen.
Unternehmen, Besichtigungsablauf und Kontakt sind als Abschnitte direkt erreichbar.
Header und Footer ergänzen diese Einstiege sowie Bildnachweise. Quelle und Lizenz
der lokal gespeicherten Aufnahme stehen in [Bildinformationen](static/images/README.md)
und auf `/bildnachweise/`. Echte Hausfotos, Lage- und Kontaktdaten sowie freigegebene
Rechtstexte sind noch zu ergänzen. Die frühere Entwurfsauswahl ist entfernt.

Anmeldung, Registrierung und Codebestätigungen verwenden ein gemeinsames Layout:
helles Einzugsmotiv neben den echten Formularen, Passwortanzeige/-hilfen und
verständliche Feldfehler. Das gemeinsame Template liegt in
`templates/registration/auth_base.html`.

Die Gebäudeansicht ist lokal unter [Gebäude erkunden](http://localhost:8000/wohnungen/gebaeude/)
erreichbar: Gebäude → Etagenplan → Wohnungsdetails. Öffentliche Wohnungsfotos können im
Mitarbeiterbereich unter **Wohnung bearbeiten → Wohnungsfotos verwalten** gepflegt werden.
Die Etagenpläne sind vereinfachte Vektorgrafiken nach den Vorlagen. Von den Wohnungsdetails
führt **Zur Besichtigung anmelden** zur wohnungsbezogenen Voranfrage; die Hauptbewerbung
wird später freigeschaltet.
Die Einrichtung, der Abgleich älterer Beispielwohnungen und die noch vorläufige räumliche
Zuordnung sind in der [Dokumentation zu US-02](docs/prototypes/16-building-apartment-view.md)
beschrieben.

Der Stack ist festgelegt. Die Foundation ist umgesetzt; die fachlichen MVP-Vertical-Slices folgen.

Statussymbole:

- ✅ entschieden oder abgeschlossen
- 🔄 in Arbeit
- ⬜ geplant
- 🚫 außerhalb des MVP

## MVP-Umfang

### Im MVP enthalten

- eine Immobilie mit 25 Einheiten
- Verwaltung der Immobilie und ihrer Einheiten
- Suche und Filter
- Detailansichten
- Anfragen von Studierenden
- Bewerbungen
- Dokumentenupload
- Datepicker für Datumsangaben
- Rollen und Berechtigungen
- lokales Entwickeln mit Docker
- Deployment auf dem Uni-Server

### Nicht im MVP enthalten

- Verwaltung weiterer Immobilien
- Bewertungssystem
- separate Frontend-Anwendung
- REST- oder GraphQL-API
- Echtzeitfunktionen
- Microservices
- individuelle UI-Komponentenbibliotheken

Bewertungen und die Verwaltung weiterer Immobilien gehören in eine spätere Roadmap.

## Technischer Stack

| Bereich | Entscheidung |
|---|---|
| Sprache | Python 3.13 |
| Backend | Django 5.2 LTS |
| Architektur | Ein Django-Monolith |
| Rendering | Serverseitige Django Templates und HTML |
| UI | UIkit 3.25.24 mit verbindlicher Komponentenpalette |
| JavaScript | UIkit JavaScript und minimales Vanilla JavaScript |
| Datenbank | PostgreSQL 18.6 |
| Datenbanktreiber | psycopg 3 |
| Dateien | Django Media-Storage mit persistentem Volume |
| Lokale Entwicklung | Docker Compose |
| Produktion | Gunicorn hinter dem Uni-Reverse-Proxy |
| Qualität | Ruff und Django Test Framework |
| Versionsverwaltung | GitHub |
| CI | Schlanker GitHub-Actions-Workflow |

## Architektur

Alle Bestandteile laufen in einem einzigen Django-Monolithen. Django-Modelle, Views, Formulare und Templates sind interne Schichten derselben Anwendung und keine separaten Services.

~~~mermaid
flowchart TD
    U["Studierende / Immobiliengesellschaft"] --> B["Browser"]
    B --> D["Django-Monolith<br/>Templates + UIkit"]
    D --> P["PostgreSQL"]
    D --> M["Media-Volume"]
~~~

## Nachweise und Dateibereinigung

Bewerber bearbeiten ihre Nachweise im eigenen freigeschalteten Entwurf. Nach der
Einreichung ist die Bewerbung unveränderbar und für Mitarbeiter einsehbar.
PDFs werden strukturell geprüft; technisch nicht verarbeitbare oder beschädigte
Dokumente werden als Formularfehler abgelehnt. Das ersetzt keinen Virenscanner.
Geschützte Downloads verwenden den bereits geöffneten Dateistream bis zum Ende
der Antwort; auch PDFs mit zusätzlichen Leerzeichen am Dateiende bleiben abrufbar.
Wer einen gespeicherten Nachweis entfernt, wird bei einer ungespeicherten
Dateiauswahl vor deren Verlust gewarnt. Abbrechen erhält die Auswahl; der Entwurf
kann anschließend zuerst gespeichert werden.

Beim Entfernen eines Nachweises werden Datenbankreferenz und Bereinigungsauftrag
in derselben Transaktion geändert. Erst nach dem Commit wird die Datei gelöscht.
Scheitert die Löschung oder endet der Prozess vorher, bleibt der Auftrag erhalten.
Offene Aufträge müssen betrieblich regelmäßig mit
`python manage.py retry_application_proof_cleanup` wiederholt werden; der Befehl
liefert bei fehlgeschlagenen Löschungen einen Fehlerstatus.

Nach einem fehlgeschlagenen Wohnungs- oder Protokollfoto-Upload werden neu
geschriebene Dateien bereinigt. Scheitert diese Bereinigung, bleibt ein Auftrag
erhalten. Offene Foto-Aufträge werden mit `python manage.py retry_handover_photo_cleanup`
wiederholt; fehlgeschlagene Löschungen liefern einen Fehlerstatus. Bereits
referenzierte Fotos werden dabei geschützt.

Beim Entfernen eines Wohnungs- oder Protokollfotos wird derselbe Bereinigungsauftrag
zusammen mit der Datenbankreferenz geändert. Erst nach dem Commit wird die Datei
gelöscht.
Scheitert die Löschung oder endet der Prozess vorher, bleibt der Auftrag für
den Wiederholungsbefehl erhalten. Dies gilt auch beim Entfernen eines Prüfpunkts
oder eines Protokollraums.

Private Uploads verwenden Dateirechte `0600` und Verzeichnisrechte `0700`.
Öffentliche statische Dateien verwenden separat `0644` und `0755`, damit ein
Reverse-Proxy sie lesen kann. Bei bereits mit privaten Rechten erzeugten
statischen Dateien müssen einmalig die Rechte in `STATIC_ROOT` korrigiert
werden (bei der Standardkonfiguration mit den folgenden Befehlen). Ein erneutes
`collectstatic` allein korrigiert vorhandene Verzeichnisse nicht. Diese Befehle
dürfen ausschließlich auf das öffentliche Static-Verzeichnis angewendet werden,
niemals auf `MEDIA_ROOT`:

```bash
find staticfiles -type d -exec chmod 755 {} +
find staticfiles -type f -exec chmod 644 {} +
```

## Technische Roadmap

| Phase | Technische Lieferobjekte | Fertigkriterium | Status |
|---|---|---|---|
| 1. Foundation | Django-Projekt, Docker Compose, PostgreSQL, Umgebungsvariablen, Ruff, CI-Grundlage | Container startet, Datenbankverbindung und Basischecks funktionieren | ✅ |
| 2. Webapp-Basis | Settings, URL-Struktur, Static/Media, Base-Templates, lokale UIkit-Assets | Eine Basis-Seite läuft mit einheitlichem UI | ✅ |
| 3. Domänenmodell | Eine Immobilie, 25 Einheiten, Anfragen, Bewerbungen und Dokumente als Django-Modelle inklusive Migrationen | Modelle, Migrationen und Testdaten funktionieren | ⬜ |
| 4. Authentifizierung | Django-User, Gruppen, Rollen und Berechtigungen für Studierende und Immobiliengesellschaft | Zugriffsschutz ist umgesetzt und getestet | 🔄 |
| 5. Verwaltungsbereich | Verwaltungsansichten und Formulare für Einheiten, Anfragen, Bewerbungen und Dokumente | Gesellschaft kann den Bestand und Vorgänge verwalten | ⬜ |
| 6. Studentenbereich | ORM-Suche, Filter, Pagination und Detailansichten | Studierende können Einheiten zuverlässig finden und ansehen | ⬜ |
| 7. Anfrage und Bewerbung | Formulare, Statusverwaltung, Datepicker, Upload-Validierung und Dateispeicherung | Kernabläufe inklusive Fehlerfällen sind getestet | ⬜ |
| 8. Qualität und Betrieb | Tests, Django-Checks, Ruff, Produktionssettings, Gunicorn, Static/Media und Deployment | CI ist erfolgreich und Deployment auf dem Uni-Server funktioniert | ⬜ |

Eine Roadmap-Phase gilt erst als abgeschlossen, wenn ihre Akzeptanzkriterien erfüllt, getestet und im zugehörigen GitHub-Issue dokumentiert sind.

## Benutzerkonten und Zugriff

Öffentliche Seiten sind ohne Konto erreichbar. Angemeldete Konten erhalten Zugriffe über feste Gruppen; zusätzliche Seitenrechte können in der Benutzerverwaltung gezielt pro Konto vergeben werden.

| Gruppe | Zugriff |
|---|---|
| `Bewerber` | Eigene Bewerbungen erstellen, Bearbeitungsstände einsehen und freigeschaltete Bewerbungen zurückziehen |
| `Mieter` | Eigene bestätigte Übergabeprotokolle ansehen und als PDF herunterladen |
| `Mitarbeiter` | Verwaltungsbereich und Übergabeprotokolle |
| `Benutzerverwaltung` | Mitarbeiterzugriff sowie Konten, Rollen und Seitenrechte verwalten |

Konten mit Mitarbeiterzugriff oder Benutzerverwaltung – auch bei direkt zugewiesenem Einzelrecht – benötigen bei jeder Anmeldung zusätzlich zum Passwort einen sechsstelligen E-Mail-Einmalcode. Der Code ist 15 Minuten gültig, wird nur gehasht gespeichert und erlaubt höchstens fünf Versuche. Es gibt bewusst keine dauerhafte Browserfreigabe. Erhält ein zuvor nicht privilegiertes Konto Mitarbeiter- oder Benutzerverwaltungsrechte, werden bestehende Sitzungen beendet; der nächste Zugriff erfordert eine neue Anmeldung mit Einmalcode. In der lokalen Entwicklungsumgebung erscheint der Code im automatisch gestarteten Mailpit-Postfach unter [http://localhost:8025](http://localhost:8025); Produktion verwendet den konfigurierten SMTP-Backend.

Die reguläre Anmeldung unter `/accounts/login/` sperrt nach drei falschen Passwörtern das betroffene Konto für 15 Minuten. Zusätzlich werden zehn fehlgeschlagene Anmeldungen derselben IP-Adresse innerhalb von 15 Minuten begrenzt. Die Anwendung speichert dafür nie die IP-Adresse selbst, sondern nur einen mit dem Servergeheimnis abgeleiteten Fingerprint. Falsches Passwort, unbekanntes Konto und Sperren liefern dieselbe neutrale Meldung. Der ungenutzte Django-Admin ist unter `/admin/` nicht erreichbar; auch Staff- und Superuser-Konten verwenden die reguläre Anmeldung mit MFA. Hinter einem Reverse-Proxy darf `DJANGO_LOGIN_THROTTLE_TRUSTED_PROXY_IPS` ausschließlich mit dessen vertrauenswürdigen IP-Adressen gesetzt werden; nur dann wird dessen `X-Forwarded-For` berücksichtigt.

Nach dem Ausführen der Migrationen wird der erste Benutzerverwalter einmalig angelegt:

~~~bash
docker compose exec web python manage.py create_initial_user_manager \
  --email verwaltung@example.test \
  --password 'ein-sicheres-passwort' \
  --first-name Verwaltung \
  --last-name Beispiel
~~~

Danach werden Konten im UIkit-Bereich **Verwaltung → Benutzer** erstellt, mit einer bestehenden konto-losen Person verknüpft oder zusammen mit einer neuen Person erfasst. Konten werden deaktiviert statt gelöscht. Die technische Rechte-Matrix und die Regel zum Ergänzen weiterer geschützter Seiten stehen in [ADR-0008](docs/decisions/0008-rollen-und-zugriffskontrolle.md).

Selbstregistrierte Bewerberkonten bleiben bis zur Eingabe eines per E-Mail gesendeten, sechsstelligen Bestätigungscodes deaktiviert. Der Code ist 15 Minuten gültig; nach fünf falschen Versuchen ist ein neuer Code anzufordern. Die lokale Entwicklungsumgebung startet dafür automatisch Mailpit. Das lokale Testpostfach ist unter [http://localhost:8025](http://localhost:8025) erreichbar und bewahrt höchstens 100 E-Mails bis zum Stoppen des Containers auf. Es werden keine E-Mails an externe Empfänger gesendet.

Mit dem Development-Override wird beim Containerstart außerdem ein ausschließlich lokales Mitarbeiterkonto bereitgestellt. Es existiert nicht in der Produktions-Compose-Konfiguration und der zugrunde liegende Command verweigert die Ausführung bei `DEBUG=False`.

| E-Mail-Adresse | Passwort | Zugriff |
|---|---|---|
| `mitarbeiter@example.test` | `KometFjord!4826` | Mitarbeiterbereich und Übergaben |

Der lokale Bootstrap reaktiviert dieses fiktive Konto und setzt sein Passwort bei jedem Entwicklungsstart auf den dokumentierten Wert zurück. Die Zugangsdaten sind absichtlich öffentlich und dürfen niemals außerhalb der lokalen Entwicklungsumgebung verwendet werden.

Für die lokale Bewerberansicht kann ein separates fiktives Konto mit dem bestehenden
Command angelegt werden:

~~~bash
docker compose exec web python manage.py create_test_applicant \
  --email ui-bewerber@example.test \
  --password 'WaldBlick!4826'
~~~

Dieses Beispielkonto ist sofort aktiv und hat ausschließlich Bewerberzugriff.
Es wird nicht automatisch beim Entwicklungsstart angelegt. Über **Wohnungen finden →
Details → Zur Besichtigung anmelden** kann eine Bewerbung erfasst werden; danach ist
sie beim Mitarbeiter unter **Bewerbungen → betreffende Wohnung** sichtbar. Eine
Hauptbewerbung wird erst nach Freigabe im Mitarbeiterbereich zugänglich. Auch diese
absichtlich öffentlichen Beispielzugangsdaten sind ausschließlich für die lokale Entwicklung.

Für den Produktivbetrieb wird der SMTP-Backend über Umgebungsvariablen konfiguriert: `DJANGO_EMAIL_BACKEND`, `DJANGO_DEFAULT_FROM_EMAIL`, `DJANGO_EMAIL_HOST`, `DJANGO_EMAIL_PORT`, `DJANGO_EMAIL_HOST_USER`, `DJANGO_EMAIL_HOST_PASSWORD`, `DJANGO_EMAIL_USE_TLS` und `DJANGO_EMAIL_TIMEOUT`. Der SMTP-Timeout beträgt standardmäßig zehn Sekunden und kann über `DJANGO_EMAIL_TIMEOUT` in Sekunden angepasst werden. Zugangsdaten gehören ausschließlich in die nicht versionierte Serverkonfiguration.

## Verwaltungsübersicht

Nach erfolgreicher Mitarbeiteranmeldung einschließlich Einmalcode öffnet sich
unter `/verwaltung/` die **Übersicht**. Ein ausdrücklich gewähltes Anmeldeziel
bleibt erhalten. Die Seite zeigt den gemeinsamen Arbeitsbestand aller Mitarbeiter;
es gibt keine persönliche Aufgabenzuordnung.

Die vier Kennzahlen führen in die bestehenden Fachbereiche:

- **Offene Bewerbungen:** Status offen und nicht zurückgezogen, ohne Altersbegrenzung.
  Der Link öffnet den Bewerbungsbereich mit der Auswahl **Offene Bewerbungen**.
- **Anstehende Besichtigungen:** geplante und bestätigte Termine aktiver Bewerbungen,
  deren Ende noch nicht erreicht ist; heute bis einschließlich des siebten Folgetags.
  Gezählt wird je Bewerbungstermin, auch bei gemeinsamen Besichtigungszeiten.
  Der Link springt zum Wochenkalender auf derselben Dashboardseite und setzt ihn
  auf die aktuelle Woche zurück; weitere Wochen sind über die Kalendernavigation erreichbar.
- **Ausstehende Rückmeldungen:** Bewerbungen mit zukünftiger, noch unbestätigter
  Besichtigung oder freigeschalteter, noch nicht eingereichter Hauptbewerbung.
  Jede Bewerbung zählt einmal; der Zeitraum ist unbegrenzt. Der Link öffnet den
  Bewerbungsbereich mit der Auswahl **Rückmeldung ausstehend**.
- **Offene Übergabeprotokolle:** gespeicherte Protokolle in Bearbeitung, ohne
  browsergebundene Formularentwürfe und ohne Altersbegrenzung. Der Link öffnet die
  bestehende Übergabeliste mit dem Filter **In Bearbeitung**, auch bei null Treffern.

Die Bewerbungsauswahl schränkt bereits die Anzahl je Wohnung ein und zeigt nur
Wohnungen mit Treffern. Sie bleibt beim Öffnen einer Wohnung, beim Zurückwechseln
zur Wohnungsübersicht und beim Blättern erhalten. Der KPI-Einstieg verwendet den
Bereich **Alle Bewerbungen**, damit offene Einzelfallprüfungen ebenfalls sichtbar
bleiben. Bei **Rückmeldung ausstehend** wird je Bewerbung angezeigt, ob die
Terminbestätigung, die Hauptbewerbung oder beides fehlt. Beide Ebenen nutzen dieselbe
Rückmeldungsregel wie die Dashboardkennzahl; weitere Filter lassen sich kombinieren
und wieder entfernen. Der normale Bewerbungsbereich behält ohne diese Auswahl sein
bisheriges Verhalten.

Die gemeinsame Aufgabenliste und die Besichtigungstageslisten bleiben im Dashboard
mit 20 Einträgen je Seite verfügbar. Alte Dashboardlinks für Bewerbungen,
Rückmeldungen und Übergaben leiten in die jeweiligen Fachbereiche weiter. Eine
zusätzliche eigenständige Kalenderansicht ist nicht Bestandteil dieser Umsetzung.

**Jetzt bearbeiten** leitet je aktiver Bewerbung einen nächsten Schritt ab:
Hauptbewerbung prüfen und final entscheiden, Besichtigungsergebnis nachtragen,
auf Hauptbewerbung warten, offenen Termin abwarten, Auswahlvoraussetzungen
prüfen, Main-Freischaltung prüfen, Bewerbung bewerten oder Besichtigung planen.
Ein abgelaufener offener Folgetermin bleibt auch bei bereits freigeschalteter,
noch nicht eingereichter Hauptbewerbung als Ergebnisaufgabe sichtbar. Nach dem
Erfassen des Ergebnisses gilt wieder der Wartezustand. Eingereichte Hauptbewerbungen
behalten Vorrang. Wartezustände erscheinen außerhalb der Mitarbeiteraufgaben.
Offene Übergabeprotokolle ergänzen die Aufgaben. Abgelaufene Besichtigungen stehen
zuerst, danach eingereichte Hauptbewerbungen, anschließend die übrigen Aufgaben; innerhalb jeder Gruppe steht
der älteste Vorgang zuerst. Neben den vier kompakten Kennzahlen zeigt die Vorschau
höchstens drei Aufgaben mit Arbeitsschritt, Wohnung und Bewerber. Der Link zur
vollständigen Aufgabenliste nennt die Gesamtzahl; dort bleiben Prüfgründe und
Zeitangaben sichtbar. Unterhalb folgt der Wochenkalender über die gesamte Breite.
Auf dem Desktop haben die beiden KPI-Reihen zusammen und das Aufgabenfeld dieselbe
feste Höhe, unabhängig von der Aufgabenanzahl. Bei längeren Aufgabeninhalten scrollt
die Liste innerhalb des Felds. Auf schmalen Bildschirmen bleibt die Höhe flexibel.
Warme Flächen, Typografie und Symbole greifen die Gestaltung der öffentlichen
Startseite auf. Alle KPI-Kacheln sind einheitlich gestaltet; der Kopfbereich bleibt ohne Foto.
Die Rückmeldungsvorschau zeigt höchstens fünf Einträge.
Aufgaben und Rückmeldungen sind über den gesamten Eintrag anklickbar und öffnen
die vorhandenen Detailansichten; separate Ansehen-Buttons entfallen.
Ein Dashboardaufruf verändert keine fachlichen Daten.

Der **Besichtigungskalender** zeigt Montag bis Sonntag der aktuellen Woche und
erlaubt das Blättern in zukünftige Wochen. Beim Wochenwechsel wird nur der Kalender
aktualisiert; die Seite und ihre Scrollposition bleiben erhalten. Browser-Zurück
und -Vorwärts stellen die gewählte Woche wieder her. Ohne JavaScript funktionieren
die Links weiterhin über normale Seitenaufrufe. Eine Animation ist noch nicht enthalten.
Pro Tag erscheinen höchstens drei noch
nicht beendete Termine; bei weiteren Terminen führt ein Link zur vollständigen
Tagesliste. Auf schmalen Bildschirmen stehen die Tage untereinander. Alle Zeiten
und Tagesgrenzen gelten in `Europe/Berlin`. Das Blättern verändert die feste
Kennzahl für heute und die nächsten sieben Tage nicht.
Die Parameter `woche` und `datum` erwarten `YYYY-MM-DD`; andere Formate fallen auf
die aktuelle Woche beziehungsweise die Standardterminliste zurück.

Eingereichte Hauptbewerbungen bleiben bis zu ihrem fachlichen Abschluss als
Mitarbeiteraufgabe sichtbar. Die Erfassung einer finalen Zu- oder Absage ist noch
nicht Bestandteil der Anwendung und bleibt eine gesonderte Folgeaufgabe. Ebenso
bleiben das Einblenden anderer Kalender, Kalenderabonnements und Synchronisation
einem separaten Folgeissue nach Fertigstellung des Dashboards vorbehalten.

## Bewerbungen im Betreiberbereich

Die Mitarbeiternavigation zeigt **Wohnungen finden** und **Gebäudeansicht**
weiterhin an. Mitarbeiter können das öffentliche Angebot direkt prüfen und
zusätzlich ihre freigeschalteten Verwaltungsbereiche aufrufen.
Besichtigungsanfragen werden aus dem Kontext der jeweiligen Wohnung gestartet;
die technische Bewerbungsvorschau ist kein Navigationspunkt der Website.

Unter **Bewerbungen** sehen berechtigte Mitarbeiter alle Wohnungen mit der Anzahl
zugeordneter Bewerbungen. Nach Auswahl einer Wohnung erscheint auf breiten
Bildschirmen eine kompakte Tabelle. Unter 1200 Pixeln werden dieselben Angaben als
beschriftete Bewerbungskarten angezeigt, ohne seitliches Scrollen. Name,
Personenanzahl, Haustiere, Bearbeitungsstatus, Priorität, Main-Status,
Besichtigung und Pre-Eingangsdatum bleiben in beiden Darstellungen sichtbar.
Ein Klick auf die Zeile beziehungsweise Karte öffnet die Bewerbungsdetails.
Der Link **Ansehen** bleibt für die Tastaturbedienung verfügbar; Text kann
weiterhin markiert und kopiert werden.
Auch abgelehnte, gesperrte und zurückgezogene Bewerbungen bleiben sichtbar.
Die neuesten Pre-Bewerbungen stehen zuerst; pro Seite werden 20 Bewerbungen angezeigt.

Die Detailansicht zeigt Kontaktdaten und Pre-Angaben sowie einen getrennten
Main-Bereich. Main-Nachweise werden erst nach der Einreichung sichtbar und
weiterhin ausschließlich über geschützte Downloads bereitgestellt.
Die Betreiberübersicht und Bewerbungsdetails untersagen Browser- und Proxy-Caching
über private `no-store`-Antwortheader.

Die wohnungsbezogene Übersicht trennt passende Bewerbungen, offene
Einzelfallprüfungen und alle Bewerbungen. Mitarbeiter können nach Kontaktdaten,
Personenzahl, Status, Main-Status, Priorität und Eingangsdatum filtern und nach
Eingang oder Priorität sortieren. Pro Seite erscheinen 20 Bewerbungen.
Belegungsgrenzen und Tierhaltungsprüfungen müssen für jede Wohnung begründet
eingerichtet werden. Eine Überschreitung der Belegungsgrenze führt direkt zur
Ablehnung; beim Speichern einer geänderten Grenze werden betroffene offene,
noch nicht zur Main-Bewerbung freigeschaltete Pre-Bewerbungen ebenfalls abgelehnt.
Haustierangaben lösen bei aktivierter
Tierhaltungsprüfung als einzige Abweichung eine Einzelfallprüfung aus. Eine
begründete Freigabe gilt bis zur nächsten Änderung der Anforderungen.
Die Namenssuche berücksichtigt auch vollständige Vor- und Nachnamen.
Prioritätsänderungen werden mit vorherigem und neuem Wert, Begründung,
Mitarbeiter und Zeitpunkt angezeigt; Freigaben werden ebenfalls intern protokolliert.
Eine manuelle Main-Freischaltung erfordert die Bestätigung einer positiven Mitarbeiterentscheidung
und sendet eine E-Mail. Ein fehlgeschlagener Versand hebt die Freischaltung nicht
auf und kann erneut angestoßen werden.

Besichtigungen werden je Bewerbung mit Datum, Beginn und Ende verwaltet. Mitarbeiter
können aktive, bereits bewertete und aktuell passende Bewerbungen einladen. Pro
Bewerbung ist höchstens ein offener Termin möglich; gemeinsame Besichtigungszeiten
für mehrere Bewerber sind erlaubt. Die Uhrzeiten gelten in `Europe/Berlin`.
Bewerber sehen ausschließlich eigene Termine unter **Meine Bewerbungen** und können
vor Beginn zusagen oder absagen. Eine Terminabsage beendet die Bewerbung nicht.
Eine Verschiebung setzt eine Zusage zurück und erfordert eine erneute Bestätigung.
Die Terminformulare prüfen Datum und Uhrzeiten direkt bei der Eingabe. Beim Planen
sind vergangene Tage gesperrt; für heute muss der Beginn noch zukünftig sein und
das Ende nach dem Beginn liegen. Fehler erscheinen am Feld und sperren das
Speichern. Beim ausdrücklich gewählten Nachtrag gelten die umgekehrten Datumsgrenzen.
Die serverseitige Prüfung bleibt unabhängig davon verbindlich.
Bei der Stundeneingabe in ein leeres Zeitfeld werden die Minuten tatsächlich mit
`00` vorbelegt. Bereits eingetragene Minuten bleiben bei einer Änderung der Stunde
erhalten.
Neue Termine erhalten standardmäßig eine Dauer von 30 Minuten. Änderungen an
der Endzeit legen eine neue Dauer fest, die bei Änderungen am Beginn erhalten
bleibt – unabhängig davon, welches Feld zuerst bearbeitet wurde:
`14:00–14:45` wird beispielsweise zu `15:00–15:45`. Bei bestehenden Terminen
wird die gespeicherte Dauer übernommen.
Würde die Endzeit über Mitternacht hinausgehen, muss eine Endzeit am selben Tag
gewählt werden.

Nach Terminende dokumentieren Mitarbeiter **Durchgeführt** oder **Nicht erschienen**.
Bereits erfolgte Besichtigungen können mit Begründung nachgetragen werden.
Neue Main-Freischaltungen verlangen eine durchgeführte Besichtigung derselben
Bewerbung und weiterhin eine positive Mitarbeiterentscheidung. Bereits bestehende
Main-Freischaltungen bleiben erhalten.

Einladungen, Verschiebungen und Mitarbeiterabsagen senden nach erfolgreicher
Speicherung eine E-Mail. Versandfehler ändern den Termin nicht; die aktuelle
Benachrichtigung kann erneut gesendet werden. Interne Notizen werden nicht an
Bewerber versendet. Rückzug und automatische Personenlimit-Ablehnung sagen offene
Termine ebenfalls ab; bei der automatischen Ablehnung wird eine Absage versendet.
Änderungen der Priorität oder Haustierregeln stornieren vorhandene Termine nicht,
verlangen aber eine erneute Prüfung vor weiteren Zuweisungen oder Verschiebungen.
Der interne Verlauf dokumentiert Termin- und Statusänderungen sowie Versandversuche.
Es gibt keine Selbstbuchung, Kalenderintegration, Kapazitätsprüfung oder Erinnerungen.

## Lokale Entwicklung

Übergabeprotokolle werden über **Protokoll prüfen und unterschreiben** abgeschlossen.
Mitarbeiter und Mieter unterschreiben mit Finger, Stift oder Maus auf demselben
Gerät. Fehlt die Mieterunterschrift, muss der Mitarbeiter dies begründen.
Nach erfolgreichem Abschluss steht die dauerhaft gespeicherte PDF-Fassung bereit;
Mieter finden ihre Downloads unter **Meine Übergabeprotokolle**. Für Altprotokolle
gibt es einen ausdrücklich gekennzeichneten nachträglichen Export.
Die Entscheidungen und Speicherregeln stehen in
[ADR-0014](docs/decisions/0014-pdf-export-und-touch-unterschriften.md).

Die lokale Entwicklungsumgebung läuft vollständig über Docker. Python und PostgreSQL müssen daher nicht separat auf dem Entwicklungsrechner installiert werden.

### Voraussetzungen

- Git
- Docker mit Docker Compose
  - Windows: Docker Desktop
  - macOS (Intel oder Apple Silicon): Docker Desktop
  - Linux: Docker Engine mit Compose-Plugin
- optional: IntelliJ IDEA / PyCharm oder eine andere IDE

Nach der Installation prüfen:

~~~bash
docker --version
docker compose version
~~~

Alle folgenden Befehle werden im Root-Verzeichnis des geklonten Repositories ausgeführt. In IntelliJ oder PyCharm kann dafür direkt das integrierte Terminal verwendet werden.

### 1. Lokale Umgebungsdatei anlegen

macOS / Linux sowie Git Bash unter Windows:

~~~bash
cp docker/.env.example docker/.env
~~~

Windows PowerShell:

~~~powershell
Copy-Item docker/.env.example docker/.env
~~~

Die Datei `docker/.env` ist nur für die lokale Entwicklung vorgesehen und wird nicht versioniert.

Der öffentliche Beispielschlüssel ist ausschließlich mit `DJANGO_DEBUG=1` nutzbar.
Bei `DJANGO_DEBUG=0` oder fehlender Debug-Einstellung verweigert bereits das Laden
der Settings einen fehlenden oder unsicheren `DJANGO_SECRET_KEY`. Anforderungen
und sichere Erzeugung stehen in [ADR-0018](docs/decisions/0018-ghcr-server-deployment.md).

### 2. Entwicklungsumgebung starten

Der folgende Befehl ist unter macOS, Linux und Windows PowerShell identisch:

~~~bash
docker compose --env-file docker/.env -f docker/compose.yaml -f docker/compose.dev.yaml up --build
~~~

Beim ersten Start werden die benötigten Docker-Images geladen und das Anwendungs-Image gebaut. Sobald die Container laufen, ist die Anwendung unter [http://localhost:8000](http://localhost:8000) erreichbar.

Beim Start wartet der Web-Container auf den gesunden PostgreSQL-Dienst und führt anschließend mit `python manage.py migrate --noinput` alle ausstehenden Django-Migrationen aus. Die Datenbankstruktur wird dadurch beim ersten Start angelegt und bei späteren Versionen schrittweise erweitert. Das PostgreSQL-Volume muss für normale Strukturänderungen nicht gelöscht werden.

Neue Strukturänderungen werden ausschließlich über Django-Modelle und versionierte Migrationen eingebracht:

~~~bash
docker compose --env-file docker/.env -f docker/compose.yaml -f docker/compose.dev.yaml exec web python manage.py makemigrations
docker compose --env-file docker/.env -f docker/compose.yaml -f docker/compose.dev.yaml exec web python manage.py migrate
~~~

Der Befehl läuft standardmäßig im Vordergrund. Für einen Start im Hintergrund kann `-d` ergänzt werden:

~~~bash
docker compose --env-file docker/.env -f docker/compose.yaml -f docker/compose.dev.yaml up --build -d
~~~

### 3. Projekt prüfen

Bei laufenden Containern können die Prüfungen aus einem zweiten Terminal ausgeführt werden:

~~~bash
docker compose --env-file docker/.env -f docker/compose.yaml -f docker/compose.dev.yaml exec web python manage.py check
docker compose --env-file docker/.env -f docker/compose.yaml -f docker/compose.dev.yaml exec web python manage.py test
docker compose --env-file docker/.env -f docker/compose.yaml -f docker/compose.dev.yaml exec web ruff check .
docker compose --env-file docker/.env -f docker/compose.yaml -f docker/compose.dev.yaml exec web ruff format --check .
~~~

Für eine erfolgreiche Foundation-Prüfung müssen alle vier Befehle ohne Fehler durchlaufen.

### 4. Entwicklungsumgebung beenden

~~~bash
docker compose --env-file docker/.env -f docker/compose.yaml -f docker/compose.dev.yaml down
~~~

Die persistenten Docker-Volumes für PostgreSQL und hochgeladene Dateien bleiben dabei erhalten.

`compose.dev.yaml` aktiviert den Django-Entwicklungsserver und bindet den lokalen Quellcode in den Container ein. Änderungen am Python-, Template- oder Static-Code sind dadurch direkt aus IntelliJ/PyCharm möglich. Ohne den Development-Override startet `compose.yaml` Gunicorn für lokale Prüfungen. Beide lokalen Varianten verwenden das Development-Image. Der Serverbetrieb verwendet ausschließlich `compose.prod.yaml` mit dem geprüften GHCR-Image; siehe [ADR-0018](docs/decisions/0018-ghcr-server-deployment.md).

## Foundation-Struktur

~~~text
config/                 Django-Projektkonfiguration
core/                   technische Basisansichten und Healthcheck
wohnungsverwaltung/     fachliches Datenmodell und PostgreSQL-Migrationen
templates/              serverseitige Django-Templates
static/                 lokale UIkit-Assets und Projekt-Styles
docker/                 Compose, Umgebungsvariablen und EntryPoint
.github/workflows/      schlanke CI-Prüfungen
~~~

## GitHub und Dokumentation

- GitHub Issues enthalten technische Aufgaben, Akzeptanzkriterien und Fortschritt.
- Die README zeigt den Projekt- und Roadmap-Status.
- AGENTS.md enthält verbindliche Regeln für Coding-Agents.
- Architekturentscheidungen werden unter docs/decisions/ dokumentiert.
- [ADR-0002](docs/decisions/0002-django-migrationen.md) beschreibt Django-Migrationen als Quelle der Datenbankstruktur.
- Einzelne Issue-Inhalte werden nicht vollständig in der README dupliziert.

## Portierbarkeit

Die GitHub-Actions-Pipeline veröffentlicht ARM64-Images in GHCR und deployt
sie auf den Ubuntu-Server hinter Caddy. Der Server ist als reine
Demo mit Beispieldaten und ohne echten Mailversand vorgesehen; die Zugänge stehen auf
der Anmeldeseite. Die Entscheidung und Abgrenzung zum Produktionsprofil
stehen in [ADR-0019](docs/decisions/0019-demo-server-deployment.md).
Voraussetzungen, Servereinrichtung,
GitHub-Secrets und der Releaseablauf stehen in
[ADR-0018](docs/decisions/0018-ghcr-server-deployment.md).

Die Anwendung bleibt durch Docker Compose, PostgreSQL, Umgebungsvariablen und persistente Volumes auf andere Server portierbar. 

Die persönlichen Bewerbungsseiten verwenden das gewählte Design A mit Ablaufübersicht, Statuskarten und getrennten Nachweisbereichen. Die Designvergleichsroute ist entfernt; Anmeldung und fachliche Freigabe bleiben erforderlich.
