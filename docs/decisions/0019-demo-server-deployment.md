# ADR-0019: Server als Demo mit fiktiven Daten

- Status: Angenommen; Betreiberkorrektur zur Zielumgebung
- Datum: 2026-10-19
- Bezug: #144; ergänzt ADR-0018

## Kontext

Der Betreiber möchte die Anwendung auf dem vorhandenen Server ausschließlich
ausprobieren: Bewerber- und Verwaltungsbereich mit einfachen Testkonten und
Beispieldaten. Ein echter SMTP-Zugang ist dafür nicht vorgesehen. Der erste
Main-Deploy nach PR #143 hat SSH und Image-Download erfolgreich geprüft, ist
aber vor Datenbankinitialisierung und Migrationen am fehlenden SMTP-Host
gescheitert. Die bisherige Annahme eines produktiven Einsatzes trifft nicht zu.

## Entscheidung

Der bestehende Workflow verwendet ausdrücklich `DEPLOY_MODE: demo`. Die
Build-, GHCR-, ARM64-, SSH- und Caddy-Schritte aus ADR-0018 bleiben bestehen.
Es wird kein weiterer Anwendungsservice eingeführt.

`config.settings_deployment` enthält die gemeinsamen Anforderungen für HTTPS,
konkrete Hosts, Proxy-Vertrauen, starke technische Secrets und private Dateien.
`config.settings_production` verlangt weiterhin echten SMTP-Zugang und erlaubt
keine Demo. Nur `config.settings_demo` setzt `DEMO_MODE=True` und verwendet
Djangos vorhandenes Dummy-Mailbackend: Nachrichten werden nicht versendet.
`DEBUG` bleibt ausgeschaltet; Gunicorn bleibt der Webserver.

Im Demo-Modus ist der Bestätigungscode für Registrierung und Verwaltungslogin
`000000`. Die normalen Formulare, Sitzungen, CSRF-Prüfungen, Rollen,
Codeablaufzeiten und Fehlversuchsgrenzen bleiben aktiv. Außerhalb des
Demo-Profils werden weiterhin zufällige Codes erzeugt. Ein zusätzlicher
Mailpit-Service oder Zugriff auf Serverlogs ist für die Anmeldung nicht nötig.

Der explizit geschützte Managementbefehl `setup_demo` legt nach Migrationen
initial die vorhandenen 25 Beispielwohnungen, fiktive Personen und Protokolle
an. Fünf unbewohnte Beispielwohnungen erhalten den Status `free` und
Beispielmieten, damit Voranfragen ausprobiert werden können. Zwei Konten
werden ausschließlich bei ihrem ersten Anlegen eingerichtet:

| Bereich | Benutzername | Passwort | Bestätigungscode |
|---|---|---|---|
| Bewerber | `user` | `user` | bei Registrierung `000000` |
| Verwaltung und Benutzerverwaltung | `verwaltung` | `verwaltung` | `000000` |

Das Verwaltungskonto hat die vorhandene fachliche Rolle Benutzerverwaltung,
keine Django-Staff- oder Superuserrechte. Demohinweis, Zugangsdaten und
Testcode erscheinen in der Demo-Oberfläche. Im normalen Profil sind diese
Hinweise ausgeblendet. Dies ist eine öffentlich erreichbare gemeinsame Demo;
es werden ausschließlich fiktive Angaben und Testdateien verwendet.

Ein erneutes Deployment setzt weder bearbeitete Wohnungen noch geänderte
Kontopasswörter zurück. Es gibt keinen automatischen Datenreset. Zusätzliche
Testkonten können in der Anwendung registriert oder in der Verwaltung angelegt
werden. Außerhalb des Demo-Profils verweigert `setup_demo` jede Änderung.

## Speicherung und Betrieb

Demo-Deploys verwenden eigene externe Volumes
`steimmo-demo-postgres-data` und `steimmo-demo-media-data`. Der Deploy-Benutzer
legt sie idempotent über Docker an. Die in ADR-0018 beschriebenen
Produktionsvolumes werden dafür nicht verwendet. Ein vorhandener
PostgreSQL-Container mit einem anderen Volume wird ausdrücklich abgewiesen.
Compose-Projekt und Netzwerk bleiben bei diesem Server dieselben; damit
bleiben der gemessene Proxy-Peer und Caddys Ziel `172.17.0.1:8010` bestehen.

Der Release-Modus wird in `mode.txt` und `release.json` gespeichert und auch
bei einem Image-Rollback verwendet. Ein Wechsel zwischen einem erfolgreichen
Produktionsrelease und Demo im selben Releasepfad wird abgewiesen. Die Demo
ist keine automatische Konvertierung einer vorhandenen produktiven Datenbank.

Die bereits angelegte private Datei `/srv/steimmo/shared/.env` liefert weiterhin
den unabhängigen Django-Schlüssel, das technische PostgreSQL-Passwort, Domain,
Bind-Adresse und gemessene Proxy-IP. Die dortigen SMTP-Platzhalter werden im
Demo-Profil nicht benötigt. Die einfachen Anmeldekennwörter aus der Tabelle
gelten ausschließlich für die Anwendung, nicht für SSH oder PostgreSQL.

Auf dem vom Betreiber bereits eingerichteten Server ist keine weitere
Caddy-Änderung und kein SMTP-Eintrag erforderlich. Nach Merge und grüner CI
veröffentlicht der neue Main-Lauf das Demo-Image und initialisiert die Demo.
Ein erneuter Lauf des früheren Produktionsdeploys verwendet weiterhin dessen
alten Commit und ist dafür ungeeignet.

## Prüfung

- Settings-Tests prüfen Demo ohne SMTP, ausgeschaltetes DEBUG, HTTPS und
  unveränderte Produktionsanforderungen.
- Django-Tests prüfen beide Logins, Verwaltungsberechtigungen, Registrierung
  mit Testcode, erneute Codeausgabe und Erhalt bearbeiteter Testdaten.
- Deployment-Tests prüfen Modusspeicherung, Initialisierung nach Migrationen
  sowie Abweisung eines Produktionsvorgängers oder falschen Datenbankvolumes.
- Der vorhandene Container-Smoke läuft zusätzlich im Demo-Profil mit
  absichtlich ungesetztem SMTP-Zugang. `ops/demo-smoke.py` prüft beide
  Anmeldungen über echtes HTTPS mit geprüfter CA, CSRF und Verwaltungs-Code.
- Der ARM64-Imagejob prüft das tatsächlich veröffentlichte Demo-Image.

## Folgen

Die vorgesehene Testumgebung benötigt keinen Maildienst und keine manuelle
Kontoeinrichtung. Versand und Zustellbarkeit echter E-Mails werden damit nicht
getestet. Für eine spätere produktive Nutzung bleiben ein eigener, explizit
geplanter Rollout und echte Produktionskonfiguration erforderlich.
