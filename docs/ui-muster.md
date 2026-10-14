# Gemeinsamer Seitenrahmen – US-18

## Zustands- und Usability-Prüfung vom 14. Oktober 2026

Die aktive Nachprüfung umfasst 74 Desktop-/Mobilaufrufe von 37 öffentlichen und
Mitarbeiter-Seiten bzw. GET-Zuständen, zusätzlich die Mitarbeiter-Bewerbungsdetails
und alle drei Zugangsentwürfe bei 320 Pixeln. Schwerpunkt sind verständliche
Sperren, Warnungen, nächste Schritte und leere Ergebnisse. Es wurden keine
Bewerbungen verändert, Freigaben erteilt, Dateien hochgeladen oder Protokolle
bestätigt. Weitere Bewerber-/Fehlerzustände wurden ergänzend anhand der Templates
und vorhandenen Django-Tests beurteilt; sie wurden nicht alle im Browser ausgelöst.

Gewählt ist A: gelbe Warnfläche mit Warnsymbol, Ursache und nächstem Schritt.
Die gemeinsame Vorlage `templates/partials/_status_notice.html` wird von Zugangs-,
Freischaltungs-, Abschluss-, PDF- und allgemeinen Fehlerseiten verwendet. Warnungen
bleiben gelb; echte Fehler und Ablehnungen verwenden Rot im selben Aufbau. Kleine
Formular-/Entwurfswarnungen erhalten ebenfalls das Warnsymbol und den stärkeren Rand.
Informationshinweise behalten ihre eigene Bedeutung und blaue Darstellung.
Die Vergleichsnavigation, Varianten B/C und die Parameterzweige sind entfernt.
Bei fehlendem Personenprofil bleibt der nächste Schritt die Prüfung der Zuordnung;
ein Kontowechsel wird nur bei fehlender Bewerberberechtigung angeboten.

Die erneute Prüfung findet keine Seitenüberläufe oder fehlenden Hilfstext-IDs,
zeigte folgende konkrete Usability-Nacharbeiten, die jetzt umgesetzt sind:

| Priorität | Beobachtung | Reine UI-Verbesserung |
|---|---|---|
| Hoch | Zugangssperre wirkt bisher wie eine blaue Information und bietet keinen direkten Weg zur Anmeldung. | Gewählten Warnentwurf übernehmen; Kontoprüfung bleibt unverändert. |
| Hoch | Abschlussfehler beim Übergabeprotokoll stehen erst unter der langen Zusammenfassung; im geprüften Mobilzustand bei ca. 3542 px. | Blockierenden Hinweis zusätzlich unmittelbar nach dem Seitentitel zeigen, mit Sprung zu den betroffenen Räumen/Prüfpunkten. |
| Mittel | „Anforderungen offen“ in der Bewerberübersicht erklärt die Lage, bietet aber keine passende Aktion. | Bestehende Wohnungsbearbeitung verlinken, Berechtigungen beibehalten. |
| Mittel | Neue interne Prüf-/Einladungsformulare verwenden `as_p`; erforderliche Begründungen und Bestätigungen sind nicht visuell markiert. | Vorhandene Formularbausteine und Pflichtkennzeichnung verwenden, keine Felder oder Regeln ändern. |
| Mittel | „Main-Status“, „Main-Bewerbung“ und „Pre-Bewerbungen“ sind wieder auf neuen Mitarbeiterseiten sichtbar. | Sichtbare Begriffe mit „Hauptbewerbung“ und „Bewerbung“ vereinheitlichen; interne Namen behalten. |
| Mittel | Ablehnung erscheint in der Bewerbungsübersicht als einfacher roter Text; beendete Status teilen sich die gelbe Kennzeichnung. | Ablehnung/Sperre mit deutlichem Statushinweis kennzeichnen und vom neutralen Rückzug unterscheiden; Statuslogik behalten. |
| Mittel | PDF-Fehlerseite erklärt den Fehler, bietet aber keinen direkten Rückweg; Browser-Titel ist generisch. | Seitentitel und erreichbaren Rückweg ergänzen, keine PDF-Erzeugung auslösen. |
| Klein | Bewerbungssegmente tragen `role="tablist"`, enthalten aber gewöhnliche Navigationslinks ohne Tab-Rollen. | Als beschriftete Navigation für serverseitige Ansichten auszeichnen. |

Ein Hinweis ist nicht automatisch eine Warnung: fehlende Vergleichsdaten oder
erläuternde Uploadhinweise dürfen informativ bleiben. Blockierte Aktionen brauchen
dagegen eine klare Kennzeichnung, Ursache und eine tatsächlich ausführbare nächste
Handlung. Diese Prüfung ersetzt keine vollständige Abnahme mit Assistenzsoftware.

## Grundlage und Abgrenzung

[US-17 / #45](https://github.com/STEImmo/STEImmo/issues/45) liefert das Corporate-Theme
und wurde mit [PR #72](https://github.com/STEImmo/STEImmo/pull/72) integriert:
Farben, Typografie, Abstände, Radien, Schatten und Zustände liegen zentral in
`static/css/app.css`. Das [Theme-ADR](decisions/0008-uikit-theme-design-token-architecture.md)
beschreibt diese Grundlage. Die Tokens und die lokalen UIkit-Assets bleiben bestehen.

[US-18 / #46](https://github.com/STEImmo/STEImmo/issues/46) ergänzt gemeinsame
UI/UX-Muster auf den echten Django-Seiten. Der erste Schritt umfasst Header,
mobile Navigation, Footer und die sichtbare Unternehmensbezeichnung.
Formular-, Listen- und Seitenmuster sind inzwischen für Bewerbungen,
Wohnungsdetails, Verwaltung und Übergaben übernommen. Gebäude- und Etagenansichten verwenden das gewählte Design B.

## Startseite: Unternehmen & Wohnen

Die Startseite ergänzt den gemeinsamen Rahmen um einen öffentlichen Einstieg:
Unternehmensbezeichnung und Standort, Wohnungssuche, Gebäude, Erklärung des
Besichtigungsablaufs und einen rollenabhängigen Zugang zum persönlichen Bereich.
Die Gebäudeansicht bleibt als eigene Seite erreichbar.

Gewählt ist das Unternehmensdesign mit einem fotografischen Einstieg über Würzburg,
grüner Hauptaktion, Unternehmensvorstellung und drei Schritten zur Besichtigungsanfrage.
Es ist direkt unter `/` erreichbar. Die Vergleichsleiste und der zweite Entwurf
sind entfernt; alte Entwurfslinks zeigen ebenfalls die gewählte Startseite.
UIkit-Komponenten und US-17-Tokens bleiben die Grundlage.
Die nur einmal verwendeten Startseitenabschnitte liegen zusammen in `core/home.html`.
Gebäude- und Startseite verwenden dieselbe Zusammenstellung der Fassade aus
`building_plans.building_overview`; Verfügbarkeiten werden nicht fest eingetragen.
Bei leerem oder vollständig belegtem Bestand bleibt die Wohnungssuche erreichbar.
Die Zeichnung liegt auf einer weißen Fläche im sandfarbenen Rahmen, damit sich
die helle Fassade vom Hintergrund abhebt. Etagenname und Verfügbarkeit erscheinen
als größere HTML-Links neben der Zeichnung, auf kleinen Bildschirmen darunter.
Sie schrumpfen nicht mit der SVG-Darstellung. Die Startseitenvorschau zeigt einen
engeren SVG-Ausschnitt; die eigene Gebäudeansicht behält den vollständigen Ausschnitt.
Es gibt keine neue JavaScript-Abhängigkeit.

Der sandfarbene Kontaktabschnitt endet vor einem anthrazitfarbenen Footer.
Dieser verwendet die bestehenden inversen Theme-Tokens für Hintergrund, Text,
Links und Tastaturfokus. So bleiben Seiteninhalt und abschließende Navigation
visuell eindeutig getrennt.

Die lokal gespeicherte Luftaufnahme zeigt Würzburg und die Alte Mainbrücke. Sie stammt
von Simon Waldherr (2018), Wikimedia Commons, CC BY-SA 4.0. Bildquelle, Lizenz und
Darstellung als Ausschnitt mit Überlagerung stehen unter `/bildnachweise/` und in
`static/images/README.md`. Die Seite lädt das Bild ohne externe Bilddienste.
Es ist ein Stadtmotiv, kein Foto des Mietgebäudes und keine Aussage über dessen Lage.

Unter dem Bild stehen Gebäudezeichnung und aktuelle Bestandszahlen, Unternehmen,
Besichtigungsablauf, persönlicher Einstieg und Kontaktabschnitt. `unternehmen`,
`ablauf`, `konto` und `kontakt` sind direkt verlinkbare, fokussierbare Abschnitte.
Öffentlicher Header und mobiles Menü ergänzen „Über uns“ und „Kontakt“. Der Footer
gliedert Wohnen/Verwaltung, Unternehmen, Konto und Rechtliches; dazu gehört der neue
Bildnachweis. Interne Bereichslinks und Berechtigungen bleiben erhalten. Nach einem
mobilen Ankersprung geht der Fokus an den Abschnitt; Escape führt zum Menüknopf zurück.

Noch benötigte Unternehmensinhalte: echte Haus- und Wohnungsfotos, genaue Lage,
bestätigte Ausstattungsangaben, konkretere Unternehmensvorstellung, Original-Logo,
Geschäftskontakt und freigegebene Rechtstexte. Die vorhandenen KI-Demofotos werden
nicht als Unternehmens- oder Gebäudefotos eingesetzt. Kontaktangaben bleiben als
Platzhalter gekennzeichnet.

Die Startseiten-, Gebäude- und Navigationstests sowie der manuelle Browsercheck
sichern Einstieg, Verfügbarkeiten, Links und Mobilansichten ab. US-18 bleibt offen.

Eine eigene persönliche Kontoübersicht existiert derzeit nicht. Das Kontomenü
zeigt den Anmeldenamen und die Abmeldung; persönliche Inhalte liegen in den
rollenabhängigen Bewerbungs- und Übergabebereichen. Eine Kontoübersicht ist als
mögliche Ergänzung zu klären, nicht Bestandteil dieser Startseitenänderung.

## Kontoseiten: gewähltes Design A

Der Auftraggeber hat A gewählt: helles Einzugsmotiv links, echtes Formular rechts.
Das gemeinsame Layout nutzt die gesamte Bildschirmbreite: Das Bild beginnt
direkt am linken Rand unter dem Header; das Formular behält eigene Innenabstände
und eine begrenzte Lesebreite. Auf schmalen Bildschirmen steht das Bild über dem Formular.
Anmeldung, Registrierung, E-Mail-Bestätigung und Mitarbeiter-Einmalcode verwenden
`registration/auth_base.html`. Namensfelder stehen auf dem Handy untereinander,
das Bild kompakt über dem Formular. UIkit und vorhandene Theme-Tokens bleiben die Basis.
Das Bild ist KI-generiert, als Sinnbild gekennzeichnet und unter Bildnachweise erklärt;
es zeigt keine tatsächliche Mietwohnung. Quelle/Prompt stehen in `static/images/README.md`.

`registration/_auth_field.html` liefert Labels, Pflichtkennzeichnung, Hilfen und
feldnahe Fehler. Django verknüpft Hilfen/Fehler über `aria-describedby`; Fehlerfelder
haben `aria-invalid` und einen roten Rahmen. `registration/_auth_errors.html`
zeigt allgemeine Meldungen ohne Änderung der vorhandenen Anmeldeschutz-Texte.
Gebundene Formfelder erhalten Namen/E-Mail bei Fehlern, Passwörter werden nicht
erneut ausgegeben. Passwort-Hinweise stammen aus den bestehenden Django-Validatoren.
Minimales Vanilla-JavaScript schaltet Passwörter auf Wunsch sichtbar/verborgen;
ohne JavaScript bleiben die Passwortfelder vollständig bedienbar.

CSRF, Anmeldung, Bestätigungscodes, Versandabstände, Rollen und Zugriffsschutz
bleiben bestehen. `next` wird beim Wechsel zwischen Anmeldung/Registrierung
beibehalten; vorhandene Tests prüfen die Rückkehr zum gewählten Ziel nach Anmeldung
und Bestätigung. Die beiden E-Mail-Felder auf der Bestätigungsseite haben eigene IDs.

Vergleichsroute `/design/konto/`, Vorschautemplate, Variante B und ungenutzte
Vorschau-Stile/-Tests sind entfernt. Die Kontoseiten sind regulär unter
`/accounts/login/`, `/accounts/registrieren/` und den zugehörigen Code-Seiten erreichbar.

## Bewerberbereich: gewähltes Design A

Design A ist in die echten Seiten integriert: Bewerbungsübersicht,
Besichtigungsanfrage, Hauptbewerbung/Nachweise und Rückzugsbestätigung.
Der gemeinsame Rahmen liegt in `wohnungsverwaltung/application_base.html`,
die Ablaufübersicht in `_application_progress.html`. Übersicht und Hauptbewerbung
markieren die aktuelle Phase anhand der bestehenden Bewerbung, ohne neue Statuswerte.
Der Hauptinhalt steht auf dem Handy vor der Ablaufleiste.

Die Übersicht zeigt ausschließlich eigene Bewerbungen, Status und nächste Handlung.
Eine offene Bewerbung verhindert weiterhin eine zweite. Leere Listen bieten die
Wohnungssuche an. Nach Einreichung führt die Aktion zur Ansicht der Unterlagen.
Die Anfrage behält die tatsächlichen Felder und serverseitige Wohnungsvorauswahl.
Labels, Pflichtkennzeichnung und verknüpfte Feldfehler bleiben sichtbar.

„Neue Bewerbung“ führt zuerst zur vorhandenen Wohnungssuche. Auch ein direkter
GET-Aufruf von `/uebergaben/bewerbung/neu/` führt angemeldete Bewerber dorthin.
Suche oder Gebäudeansicht → Wohnungsdetails → „Zur Besichtigung anmelden“ übernimmt
die konkrete Wohnung serverseitig. Das Formular zeigt nur eine Zusammenfassung mit
öffentlicher Nummer (001–005 im Erdgeschoss), Etage und vorhandener Wohnfläche.
„Wohnungsdetails ansehen“ und „Andere Wohnung wählen“ bieten nachvollziehbare Rückwege.
Eine zweite Wohnungsauswahl im Formular entfällt; Radiokarten, zugehörige Widgets und
Stile sind entfernt. Bereits geöffnete ältere Formulare dürfen weiterhin über die
bisherige POST-Route absenden; deren Verfügbarkeits-, Rollen- und Datenprüfung bleibt
erhalten. Vorausgewählte Wohnungen bleiben serverseitig fest gebunden. Gespeicherte
Kennungen und Bewerbungsabläufe ändern sich nicht.

Nachweise erscheinen in drei getrennten Bereichen mit vorhanden/fehlend-Anzeige.
Der Zähler erfasst gespeicherte Kategorien, nicht die Anzahl einzelner Dateien.
Mehrfachauswahl, Uploadgrenzen, Entwurf, endgültige Einreichung, Downloads und
getrennte Löschformulare bleiben erhalten. Neue Dateiauswahlen sind erst nach
Speichern Teil des Zählers. Eingereichte Nachweise sind schreibgeschützt.
Zurückziehen erfordert weiterhin die bestehende Bestätigungsseite.

Die Vergleichsroute `/uebergaben/design/bewerbungen/`, Beispieldaten und Variante B
sind entfernt. Rollen, CSRF, fachliche Validierung und Speicherlogik bleiben erhalten.
Response- und bestehende Upload-/Berechtigungstests sichern die Übertragung ab;
die echten Seiten werden zusätzlich auf localhost auf Desktop und Handy geprüft.
Die übrigen öffentlichen und internen Seiten verwenden ebenfalls gemeinsame Muster.
## Wohnungssuche: gewähltes Design A

Die überarbeitete Variante A ist regulär unter `/wohnungen/` integriert:
kompakter Seitenkopf, Filter links und Wohnungskarten rechts. Der Filter heißt
„Filter“, ist auf dem Desktop 340 px breit und bleibt beim Scrollen sichtbar.
Eingabefelder und Hauptaktion sind 48 px hoch. Bei geringer Fensterhöhe ist der
Filter selbst scrollbar; unter 960 px steht er regulär über den Ergebnissen.

Filter, Validierungen und Verfügbarkeitsregeln bleiben erhalten. Ergebniszahl und
Leermeldungen berücksichtigen nur tatsächliche Suchfelder; ungültige Werte zeigen
verknüpfte Feldfehler. „Filter zurücksetzen“ führt zur ungefilterten Suche.
Wohnungen ohne gepflegte Fläche/Miete/Zimmerzahl werden als solche bezeichnet.

Karten und Filter liegen in `apartment_search.html`; die wiederverwendeten Felder
liegen in `_apartment_search_field.html`. Vorhandene Fotos
werden über die bestehende öffentliche Foto-Route geladen; Demo-/KI-Beschriftungen
bleiben sichtbar. Details führen weiterhin zur konkreten Wohnung und von dort zur
Besichtigungsanfrage mit serverseitig übernommener Wohnung.

Vergleichsroute, Umschaltung, Varianten B/C und Vorschautemplates/-tests/-stile
sind entfernt. Reguläre UI- und bestehende Such-/Gebäude-/Klickwegtests sichern
die Integration ab. Keine neue Dependency oder Migration; US-18 bleibt offen.

## Noch offener Umfang von US-18
Der Seitenrahmen ist ein Teil der Story. Die geplanten 6–8 Stunden gelten für
die gesamte Umsetzung einschließlich der Prüfung; sie sind keine gemessene
Arbeitszeit und keine Zusage für ein vollständiges Redesign aller Seiten.
Für die restliche Umsetzung gelten folgende konkrete Arbeitspakete:

- Gemeinsamer Seitenkopf mit Seitentitel, Erklärung, Hauptaktion und Rückweg;
  auf öffentlichen und internen Seiten einsetzen. Die bestehende Palette aus
  US-17 auch in Inhaltsbereichen erkennbar anwenden.
- Formularmuster für sichtbare Labels, Pflichtfelder, Hilfen, feldnahe Fehler
  sowie Speichern und Abbrechen; das erprobte Kontomuster auf Bewerbung und
  Verwaltungsformulare übertragen.
- Wohnungsdetails, Gebäude-/Etagenansichten und interne Listen vereinheitlichen;
  Tabellen, Karten, Filter und Aktionen auch auf kleinen Bildschirmen bedienen können.
- Gemeinsame Muster für leere Listen, Erfolg, Warnungen, Fehler und tatsächlich
  vorhandene Upload-/Ladezustände anwenden. Keine künstlichen Ladeanimationen ergänzen.
- Relevante Seiten und Zustände mit den vorhandenen Rollen prüfen; Browser,
  Tastatur, Mobilansicht, Response-Tests, Dokumentation und unabhängiges Review abschließen.

Der Bewerberablauf ist als UI-Teilumsetzung integriert. Als Nächstes werden die
erprobten Seiten-, Formular- und Statusmuster auf die Wohnungsansichten und die
relevanten Verwaltungsseiten übertragen.

## Begriffe in der Oberfläche

Öffentliche und persönliche Seiten verwenden „Bewerbung“ und im konkreten
Besichtigungskontext „Besichtigungsanfrage“. Die spätere Stufe heißt
„Hauptbewerbung“; die Aktion in der Übersicht heißt „Bewerbung vervollständigen“.
Mitarbeiterdetails unterscheiden Besichtigungsanfrage und Hauptbewerbung.
Technische URL-Namen, Klassen und der bestehende Freigabeprozess bleiben erhalten.

## Unternehmensbezeichnung

STEImmo bleibt ein interner Projektname. Im Header, Footer, Seitentitel und
auf der Startseite steht **STE Immobilien eGbR**. Für die Hauptwebsite hat der
Auftraggeber die allgemeinere Beschreibung „Wohnungsvermietung in Würzburg“ gewählt.

Quellen aus dem vom Nutzer bereitgestellten Projektordner:

- [Projektauftrag](https://drive.google.com/file/d/1JB1tjn_AXOKnsVgeyRxmL4uWN2z2KR77): Firmierung des Projektkunden.
- [Projektpitch](https://drive.google.com/file/d/1Z6vXQ0n6QF-1dPcyZrBSp2pUK5_UGXj5/view): Schwerpunkt auf Studierendenwohnungen im Raum Würzburg.

Es werden keine privaten Kontakt- oder Bewerberdaten aus den Unterlagen übernommen.
Die gelesenen Unterlagen erweitern nicht den in README und AGENTS festgelegten MVP.
Eine Original-Logodatei ist noch nicht eingebunden; die Firmenwortmarke dient bis dahin als Darstellung.

## Ablage und Verhalten

`templates/base.html` bindet die folgenden app-übergreifenden Partials ein:

| Datei in `templates/partials/` | Aufgabe |
|---|---|
| `_site_header.html` | Firmenwortmarke, Desktopnavigation, Konto und mobiles UIkit-Offcanvas |
| `_navigation_links.html` | Gemeinsame Linkliste für Desktop, Mobil und Footer |
| `_account_actions.html` | Anmelden, Registrieren oder CSRF-geschütztes Abmelden per POST |
| `_site_footer.html` | Unternehmensbezeichnung, Kontaktlink, Navigation und rechtliche Informationen |

Die Linkliste übernimmt die vorhandenen Berechtigungsbedingungen einschließlich
Mehrfachrollen und Einzelrechten. Die öffentlichen Links führen zur Wohnungssuche
und Gebäudeansicht und bleiben auch für Mitarbeiter sichtbar. Die technische Bewerbungsvorschau ist kein Navigationspunkt;
Besichtigungsanfragen gehören zum Kontext der jeweiligen Wohnung.
Aktuelle Seiten verwenden `aria-current="page"`,
übergeordnete Bereiche `aria-current="true"`. Die aktive Position wird zusätzlich
unterstrichen. Ein Sprunglink führt zum Hauptinhalt.

Unterhalb von 1200 Pixeln ersetzt ein beschrifteter Menüschalter die Desktopnavigation.
Das UIkit-Offcanvas erhält beim Öffnen den Fokus auf den ersten Navigationslink;
beim Schließen kehrt der Fokus zum Menüschalter zurück. Das kleine Vanilla-Script
`static/js/site-navigation.js` hält den auf-/zugeklappten Zustand synchron.

Header und Footer verwenden ausschließlich die Theme-Tokens. Das helle mobile
Menü und das Kontomenü verwenden einen blauen Fokusrahmen; die dunkle Navbar
verwendet die bestehende inverse Fokusfarbe.
Die Footer-Spalten dürfen bei vielen Rollenlinks umbrechen.
Auf Anmeldung und Registrierung übernehmen die Kontolinks auch im mobilen Menü
das vorhandene `next`-Ziel, damit die ausgewählte Wohnung erhalten bleibt.

## Erreichbarkeit nach Integration der Gebäudeansicht

Die echte Gebäudeansicht aus #16 ist integriert. Die Übergangsroute und ihr
Platzhalter-Template sind entfernt. Header, mobiles Menü und Footer verlinken
direkt `wohnungsverwaltung_public:building_view`.

Ab der Startseite sind die regulären Seiten über echte Links innerhalb von
höchstens drei Klicks erreichbar. Die Linkprüfung verwendet synthetische Daten
in der isolierten Testdatenbank und prüft auch die HTTP-Antwort jeder Zielseite.

| Rolle / Ziel | Weg ab Startseite | Klicks |
|---|---|---|
| Gäste: Suche, Gebäude, Anmeldung, Registrierung | Gemeinsame Navigation bzw. Kontolinks | 1 |
| Alle: Impressum, Datenschutz | Footer → Rechtliches | 1 |
| Alle: Kontakt | Header/Footernavigation → Kontaktabschnitt der Startseite | 1 |
| Alle: Anbieter-Kontaktangaben | Kontaktabschnitt → Impressum | 2 |
| Alle: Bildnachweise | Footer → Bildnachweise | 1 |
| Gäste: Etage | Gebäudeansicht → Stockwerk | 2 |
| Gäste: Wohnungsdetails | Wohnungssuche → Details; alternativ Gebäude → Etage → Wohnung | 2–3 |
| Gäste / Bewerber: Besichtigungsanfrage | Wohnungssuche → Details → Zur Besichtigung anmelden | 3 |
| Bewerber: neue Bewerbung | Wohnungssuche → Details → Zur Besichtigung anmelden | 3 |
| Bewerber: freigeschaltete Hauptbewerbung / Rücknahme | Meine Bewerbungen → Bewerbung vervollständigen → Zurückziehen | 2–3 |
| Mieter: eigene Übergabeprotokolle | Meine Übergabeprotokolle | 1 |
| Mitarbeiter: Wohnung, Räume, Fotos | Verwaltung → Wohnung bearbeiten → Raum oder Fotos | 2–3 |
| Mitarbeiter: Stellplätze und Merkmale | Verwaltung → Liste → Anlegen oder Bearbeiten | 3 |
| Mitarbeiter: Übergabeprotokoll und Unterseiten | Übergaben → Protokoll → Bearbeiten, Raum, Schlüssel oder Unterschriften | 2–3 |
| Mitarbeiter: Bewerbungsdetails | Bewerbungen → Wohnung → Bewerbung | 3 |
| Kontoverwaltung: Benutzer anlegen / bearbeiten | Benutzer → Anlegen oder Bearbeiten | 2 |

Auf dem Handy benötigt das Öffnen des Header-Menüs einen zusätzlichen Klick.
Die Bereichslinks stehen deshalb auch direkt im Footer bereit; über diesen Weg
bleibt die Grenze von drei Klicks erhalten. Scrollen und automatische Weiterleitungen
zählen nicht als Klick. Eine erforderliche Anmeldung und fachliche Freigaben
bleiben Teil des jeweiligen Ablaufs.

Codebestätigung, Mitarbeiter-MFA und zustandsabhängige Bestätigungsseiten werden
im passenden Ablauf erreicht. Downloads, technische Endpunkte und ausschließlich
per POST ausgeführte Aktionen sind keine eigenständigen Navigationsseiten.
Die technische Bewerbungsvorschau bleibt bewusst ohne Link in der Hauptwebsite.

Automatisierte Prüfung: `core/test_navigation_reachability.py` ergänzt die
gemeinsamen Navigations- und Berechtigungsprüfungen in `core/test_site_navigation.py`.

## Vorschau und offene Punkte

Der Seitenrahmen ist als Teilumsetzung von US-18 für einen Commit bereit:
Startseite über die Firmenwortmarke, öffentliche Suche/Gebäude, Kontozugänge,
rollenabhängige Bereiche, mobile Bedienung sowie Kontakt, Impressum und Datenschutz
sind erreichbar. Besichtigungsanfragen beginnen weiterhin bei der Wohnung.
Diese Freigabe betrifft die UI-Struktur; die Unternehmensangaben und Rechtstexte
sind weiterhin ausdrücklich gekennzeichnete Entwürfe. Die gesamte Story bleibt offen.

Die Oberfläche wird direkt auf [localhost:8000](http://localhost:8000/) geprüft,
insbesondere [Wohnungssuche](http://localhost:8000/wohnungen/) und
[Anmeldung](http://localhost:8000/accounts/login/). Es gibt keinen separaten
Header-/Footer-Prototyp mehr.

- Das Original-Logo kann später in den gemeinsamen Header eingebunden werden.
- Impressum und Datenschutz sind im Footer verlinkt und als Layoutentwürfe unter
  `/impressum/` und `/datenschutz/` erreichbar. Ihre Platzhalter sind keine fertigen
  Rechtstexte. Das Unternehmen ergänzt und prüft die verbindlichen Angaben vor Veröffentlichung.
- Die integrierte Gebäudeansicht ist unter `/wohnungen/gebaeude/` erreichbar.
  Gebäude- und Etagenansicht markieren den eigenen Navigationsbereich.
- US-18 bleibt offen, bis auch die übrigen UI/UX-Muster umgesetzt und abgenommen sind.

## Übernommene Einzelansichten und Dateiumfang

Wohnungsdetail A, Verwaltung B und Übergaben B sind in die echten Django-Seiten
übernommen. Das Wohnungsdetail zeigt die vorhandene Galerie, eine kompakte
Eckdatenzeile ohne farbige Karte und Mietangaben im normalen Seitenfluss.
Die Besichtigungsaktion verwendet weiterhin den bestehenden wohnungsbezogenen Ablauf.

Alle zwölf Verwaltungsansichten verwenden eine horizontale Bereichsnavigation,
kompakte Tabellen und gegliederte Formulare. Die neun Übergabeansichten verwenden
dasselbe Orientierungsmuster, kompakte Karten und bei ausreichender Bildschirmbreite
zwei Spalten. Vorhandene Aktionen, Fehleranzeigen, Formsets, CSRF, Uploads,
Unterschriften, Entwürfe und Berechtigungen bleiben bestehen. Mieter sehen ihre
zugeordneten Protokolle; Verwaltungslinks bleiben rollenabhängig.

Die Entwicklungsvorschau `/design/seiten/` und ihre neun temporären Dateien sind
entfernt. Nur einmal verwendete Startseitenabschnitte und die Filterhülle sind
in die bestehenden Seiten zurückgeführt. Die nur in der Suche verwendete
Ergebniskarte ist ebenfalls in die Suchseite integriert. Mehrfach verwendete
Formular- und Navigationsbausteine bleiben als Partials. Das neue
`_workspace_navigation.html` bündelt die Bereichsnavigation der 21 internen Seiten.
Das ausgewählte CSS liegt ausschließlich im bestehenden `static/css/app.css`.

Gegenüber dem gemeinsamen Ausgangsstand des UI-Branches verbleiben 28 neue
dauerhafte Dateien: 15 Templates, sieben Testmodule, zwei Dokumentationen,
zwei Bildassets und zwei kleine JavaScript-Dateien. Benutzerseitige lokale
Dateien werden dabei nicht mitgezählt. Die Übernahme der 21 internen Ansichten
ändert bestehende Templates; es entsteht keine Datei pro Variante.

Validierung: 191 Tests für öffentliche Seiten und Verwaltung sowie 504 Tests
der Wohnungsverwaltung erfolgreich (teilweise überlappende Testgruppen).
Django-Systemcheck, Migrationsprüfung, Ruff und Diff-Prüfung erfolgreich.
Browser-Smoke auf echten Wohnungsdetails, Mitarbeiteranmeldung, Verwaltung,
Wohnungsformular, Übergabeübersicht/-detail, Protokollbearbeitung, Raumprüfung,
Schlüssel und Abschlussansicht durchgeführt. Keine Testdaten über die
Formulare gespeichert und kein Protokoll unterschrieben oder bestätigt.

Gebäude und alle fünf Etagen verwenden das ausgewählte Design B auf den
echten Seiten `/wohnungen/gebaeude/` und `/wohnungen/etagen/0/` bis `/wohnungen/etagen/4/`.
Die Gebäudeangaben stehen schlicht unter der Fassade. Der große Grundriss führt
zu vergleichbaren Wohnungszeilen mit umrahmten Detailbuttons. Bestehende
Zeichnungen, Daten, Verfügbarkeitsregeln und Etagenlinks bleiben erhalten.
Vergleichsvorlage, A-/C-Stile und Vorschauauswahl sind entfernt; alte Links mit
Entwurfsparametern zeigen ebenfalls die echte Ansicht. Das gilt auch in Produktion.

Der Zugriffshinweis bei fehlender Bewerberrolle und die historische technische
Bewerbungsvorschau verwenden ebenfalls den gemeinsamen Seitenrahmen. Die
technische Vorschau bleibt ohne Navigationseintrag und ohne Speichermöglichkeit.
Damit sind alle regulären MVP-Seiten gestalterisch abgedeckt. Für den vollständigen
UI-Abschluss fehlen noch eigene allgemeine Fehlerseiten (403/404/500 sowie
Uploadlimit-Antwort), abschließende Sichtung/Abnahme und die Freigabe über PR/Review.
Rechtstexte, Kontaktangaben, Originalbilder und bestätigte Wohnungsdaten bleiben
inhaltliche Aufgaben. Zimmerzahlen werden weiterhin aus dem vorhandenen Feld
gelesen; im geprüften lokalen Bestand sind bei allen 25 Wohnungen nur die
Standardwerte 0,00 hinterlegt. Fehlende Angaben werden ausdrücklich angezeigt.
Die Dokumentation bleibt lokal; das ursprüngliche GitHub-Issue wird nicht verändert.

Abschlussprüfung dieser Übernahme: 160 Tests für Core, öffentliche Ansichten,
Wohnungssuche und Bewerbungsoberfläche sowie System-, Migrations-, Ruff- und
Diff-Prüfungen erfolgreich. Die Geschäftslogik und das Datenbankschema sind unverändert.

### Gestaltungsprüfung nach der Übernahme

Hinweisboxen haben unabhängig von der zusätzlich vorhandenen UIkit-Basisklasse
einheitliche Innenabstände: 16 Pixel oben/unten und 24 Pixel links/rechts.
Damit sind auch die Farbvarianten bei Formularfehlern, Entwürfen und Statushinweisen
abgedeckt. Der Entwurfshinweis nutzt eine umbruchfähige Aktionszeile mit 12 Pixel
Abstand zwischen den Buttons, ohne negative UIkit-Gridränder.

Die erreichbaren 29 Seiten wurden auf Desktopbreite und mit 320 Pixel Breite
auf horizontale Überläufe geprüft. Zusätzlich wurden die vorhandenen Templates
für Konten, Bewerbungen, Verwaltung und Übergaben auf gemeinsame Abstände,
Tabellendarstellung, Formularlabels und Aktionsbereiche geprüft.

Korrigiert sind der Mauszeiger des überlagerten Foto-Dateifelds, der Abstand
zwischen Schlüsselkopf und Tabelle, die identische obere Ausrichtung der
Abschlusskarten und die doppelten UIkit-Abstände in CSS-Grids. Raumüberschriften
und Aktionen können auf schmalen Bildschirmen umbrechen; die Verwaltungstabelle
der Räume ist seitlich scrollbar. Ein einzelnes Raumformular nutzt die gesamte
Arbeitsfläche. Verwaltungs- und Übergabebuttons verwenden dieselbe normale
Schreibweise wie die übrigen Bereiche.

Für diese Korrekturen sind keine weiteren Dateien und keine fachlichen
Änderungen entstanden. Die 111 betroffenen UI-, Verwaltungs-, Übergabe- und
Exporttests sowie Django-, Migrations-, Ruff- und Diff-Prüfungen sind erfolgreich.
Nicht jeder mögliche Datenzustand ist durch den Browser-Smoke abgedeckt;
Rollenschutz und seltene Formular-/Exportzustände werden zusätzlich durch
die bestehenden Django-Tests geprüft.

## Allgemeine Fehlerseiten

HTTP 400, 403, 404 und 500 verwenden eine gemeinsame, schlichte Fehlerseite mit
Fehlernummer, verständlichem Hinweis und Links zu Startseite und Wohnungssuche.
Dieselbe Vorlage zeigt Formular-Sicherheitsfehler und bestehende Upload-Limits
(413) an. Statuscodes, Upload-Grenzen und Schutzmechanismen bleiben erhalten.
Die Vorlage verwendet keinen Request-Kontext und benötigt keine Datenbankabfrage;
auch bei einem Datenbankausfall bleibt die Fehleranzeige verfügbar.
Bei aktiviertem Django-Debugmodus bleiben die technischen 400-/404-/500-Seiten
für die Entwicklung sichtbar. Die gestalteten Seiten greifen im Betrieb mit
`DEBUG=False`; 403 und Formular-Sicherheitsfehler sind auch lokal gestaltet.

Inhaltliche Ergänzungen und neue Funktionen wie eine Profilseite werden als
eigene Aufgaben behandelt. Neue Issues werden erst nach gesondertem Auftrag angelegt.

## Rechtliche Inhalte vor Veröffentlichung

Die Layoutentwürfe sind auf Wunsch des Auftraggebers vorbereitet. Noch zu ergänzen
sind insbesondere Geschäftsanschrift, Vertretung, Geschäftskontakt und Registerangaben.
Die Datenschutzhinweise müssen die tatsächlichen Produktionsdienste und die Verarbeitung
bei Konto, Besichtigungsanfragen, Bewerbungen, Dokumenten und Übergabeprotokollen abdecken.
Auch Zwecke, Rechtsgrundlagen, Empfänger, Fristen und Rechte benötigen verbindliche Angaben.
Die Verantwortung für die abschließenden Inhalte liegt beim Unternehmen.

Grundlagen für diese Inhaltsstruktur:

- [§ 5 DDG](https://www.gesetze-im-internet.de/ddg/__5.html): Anbieterinformationen.
- [Art. 13 DSGVO](https://eur-lex.europa.eu/legal-content/DE/TXT/?uri=CELEX:32016R0679): Informationen bei Erhebung personenbezogener Daten.
- [§ 25 TDDDG](https://www.gesetze-im-internet.de/ttdsg/__25.html): Endgerätezugriff; technisch notwendige Funktionen und optionale Dienste unterscheiden.

Cookie-Einstellungen werden erst erforderlich, wenn tatsächlich einwilligungsbedürftige
Dienste eingesetzt werden. Es wird keine zusätzliche Tracking- oder Consent-Bibliothek eingeführt.


## Abschließende UI-Prüfung und Hinweise für die PR

Pflichtfelder der internen Formulare sind anhand der vorhandenen Django-Felder
markiert. Hilfs- und Fehlermeldungen besitzen die von Django referenzierten IDs.
Übergabetabellen verwenden beschriftete, fokussierbare Scrollregionen und
Spaltenüberschriften. Fokusfarben der Zeichnungen/Galerie nutzen den zentralen
Token; die kleine Fassadenbeschriftung verwendet den kontrastreicheren Text-Token.

Auf dem Handy ist der Filter anfangs eingeklappt und über eine beschriftete
Schaltfläche erreichbar. Ungültige Filter halten ihn offen; ohne JavaScript bleibt
das gesamte GET-Formular sichtbar. Auf dem Desktop bleibt der breite Filter stehen.
Suchwerte, Filterprüfung, Ergebniszusammenstellung und URLs ändern sich nicht.

Die Übergabe ergänzt ausschließlich sichtbare Lade-/Fehlerrückmeldungen und
`aria-busy` beim vorhandenen Nachladen. Anfragen, Datenübernahme und Rückgabewerte
bleiben bestehen; Netzwerkfehler werden weiterhin weitergegeben. Für die PR:
Das bestehende Verhalten bei HTTP-Fehlern (bisherige abhängige Angaben bleiben
stehen) sowie bei überlappenden Anfragen wird damit nicht fachlich abgesichert.
Rücksetzen, Abbruch oder Reihenfolgekontrolle wären separate Logikänderungen.

Bilder sind bei gleichen Abmessungen und unverändertem Motiv neu komprimiert.
Dateiformat des Kontomotivs: WebP. Quellen, Lizenz und sichtbare Kennzeichnung
bleiben erhalten. Es gibt keine neue Abhängigkeit und keine neue Template-Datei.

Unternehmensinhalte, Rechtstexte, gepflegte Miet-/Zimmerangaben, Originalfotos und
eine Profilseite bleiben getrennte Aufgaben. Keine Issues dafür eigenständig anlegen.

## Stand vor der PR – 13. Oktober 2026

Die abschließende Browserprüfung umfasst erneut 102 Aufrufe der erreichbaren
öffentlichen und Mitarbeiteransichten bei 1440, 390 und 320 Pixeln. Keine
Seitenüberläufe, fehlenden Feldbeschriftungen, defekten Hilfstext-Verknüpfungen
oder kaputten Bilder gefunden. Seltene Datenzustände und andere Kontorollen
werden ergänzend über Templates und Django-Tests geprüft, nicht vollständig visuell.

Die vollständige lokale Suite umfasst 607 Tests. Ein veralteter Navigationstest
schlug in drei Rollen-Unterfällen fehl, weil er noch ausgeblendete öffentliche
Links erwartete. Seine Erwartung ist an die freigegebene Navigation angepasst;
die zehn Zugriffsschutztests wurden danach erfolgreich erneut ausgeführt.
Die übrigen Tests der vollständigen Suite waren erfolgreich. Django-Check,
Migrationsprüfung, Ruff und Diff-Prüfung werden vor der PR ebenfalls ausgeführt.

Der UI-Branch enthält gegenüber seinem gemeinsamen Ausgangspunkt mit main
29 neue und 58 geänderte Dateien, einschließlich Tests, Bildern und Dokumentation.
Temporäre Vergleichsseiten sind entfernt. AGENTS.md, UIkit-Vendor-Dateien und
Migrationen wurden durch die UI-Arbeit nicht verändert.

Wichtig für die PR: Neben Templates/CSS enthält die Umsetzung Anzeige-Kontext
in Views, einheitliche Wohnungsbezeichnungen und den ausdrücklich abgestimmten
GET-Einstieg zur Bewerbung über die Wohnungssuche. Alte POST-Einstiege bleiben
erhalten. Nicht pauschal als ausschließlich CSS-Änderung beschreiben; Datenmodell,
Validierung, Statuswechsel und Berechtigungen werden nicht fachlich neu definiert.

Der remote main-Stand a4572bf enthält inzwischen weitere Formularverbesserungen
und Bewerberfilter. Die rein lokale Merge-Simulation ergibt 17 Dateikonflikte,
überwiegend in Templates sowie in wohnungsverwaltung/views.py. Es wurde kein
Merge ausgeführt. Vor Ready for Review sind diese Änderungen zu integrieren,
Konflikte unter Erhalt der fachlichen Funktionen zu lösen und der gemeinsame
Stand erneut zu prüfen. Bis dahin die PR mit Refs #46 statt Closes #46 vorbereiten.

## Korrekturen aus dem Review vom 14. Oktober 2026

Verwaltungslisten, Raumlisten, Bewerbungslisten und die Übergabeübersicht nutzen
UIkits `uk-table-responsive`: Unter 960 Pixeln stehen die Felder je Eintrag
untereinander mit sichtbaren Spaltenbezeichnungen. Aktionen bleiben ohne
seitliches Scrollen zugänglich. Die pauschale Mindestbreite von 620 Pixeln ist
entfernt. Fachliche Vergleichstabellen im Protokoll bleiben gezielt scrollbar.

Die Übergabenavigation führt mit „Räume“ und „Schlüssel“ zu den vorhandenen
Abschnitten des Protokolls. Hinzufügen bleibt eine gesonderte Aktion. Raum- und
Schlüsselunterseiten markieren ihren jeweiligen Bereich. Drei einfache
Übergabeformulare verwenden das bestehende Feld-Partial für Labels, Hilfstexte,
Pflichtkennzeichnung und Fehler. Schlüsselstatus erhalten im Formular deutsche
Anzeigetexte; gespeicherte Werte und Datenbankschema bleiben unverändert.

Ungültige Suchfilter zeigen ausschließlich die Korrekturaufforderung statt
einer Trefferzahl und eines vermeintlichen leeren Ergebnisses. Gültige Suchen
ohne Treffer behalten ihren Leerzustand und den Link zum Zurücksetzen.

Angemeldete Nutzer erhalten auf der Startseite unterhalb des Headers direkte
Bereichslinks, wenn der Desktop-Header ausgeblendet ist. Diese verwenden dasselbe
rollenabhängige Navigations-Partial. Damit benötigen die Hauptwege ab Startseite
kein Öffnen des mobilen Menüs und keinen Umweg zum Footer. Die Drei-Klick-Angabe
bezieht sich auf Seitenwechsel über direkte Links; Anmeldung, Bestätigungscodes,
Formulareingaben und Absenden sind zusätzliche Schritte. Die Linktests ersetzen
keine visuelle oder vollständige Interaktionsprüfung.

IDE-Dateien werden über `.gitignore` ausgeschlossen. Die beiden Filter-SVGs sind
weiterhin unversionierte Entwürfe und keine Laufzeitabhängigkeit. Ihre Aufnahme
in einen PR ist nur bei einem bewussten Dokumentationszweck sinnvoll.

Die Integration der 17 Konfliktdateien mit dem bekannten main-Stand bleibt offen.
Empfohlen ist zuerst ein lokaler Merge mit `--no-commit --no-ff`, dann die
Konfliktlösung unter Erhalt der fachlichen Erweiterungen aus main und abschließend
die vollständige Prüfung. Ein solcher Merge wurde für diese UI-Korrekturen nicht
begonnen. Es erfolgen keine GitHub-Änderungen, Commits oder Pushes ohne Auftrag.

Verifikation dieses lokalen Stands: 611 Django-Tests erfolgreich. Django-Check,
Migrationsprüfung, Ruff-Lint, Ruff-Formatprüfung und Diff-Prüfung erfolgreich.
Browser-Smoke: Listen und Aktionen bei 320/390 Pixeln, deutsche Schlüsselstatus,
mobile Direktzugänge, Raumanker mit Fokus und korrigierter Filterfehlerzustand.
Die Mitarbeiter-Navigation wurde zusätzlich bei 1200 Pixeln ohne Seitenüberlauf
geprüft. Andere Rollen sind über die bestehenden Berechtigungs- und Navigationstests
abgedeckt; kein vollständiger Geräte- oder Screenreader-Audit.

Die vollständige Gebäudeansicht schneidet den ungenutzten SVG-Bereich oberhalb
des Dachs ab (viewBox: 0 110 1100 680). Zeichnung, Etagenlinks und der gesonderte
Ausschnitt der Startseitenvorschau bleiben erhalten.

## Integration mit main – 14. Oktober 2026

Die 17 Konfliktdateien des bereits gestarteten Merges mit `origin/main` (a4572bf)
sind lokal kombiniert. Das UI-Layout und die mobilen Tabellen bleiben erhalten;
Bewerberfilter, Prioritäten, Einladungen, interne Prüfungen und die neuen
Wohnungsanforderungen aus main werden vollständig angezeigt. Automatische
Ablehnungen bleiben für Bewerber verständlich sichtbar. Die gemeinsamen
Formularhilfen aus main ergänzen die vorhandenen Labels und Pflichtkennzeichnungen.

Beim Nachladen der Übergabeangaben bleiben die zeitbezogene Auswahl historischer
Vergleiche, der Schutz vor veralteten Antworten und die Erhaltung bereits
bearbeiteter Felder aus main erhalten. Lade-, Fehler- und Erfolgsmeldungen sowie
`aria-busy` aus dem UI-Branch sind damit verbunden; nur die aktuelle Anfrage
aktualisiert die Rückmeldung und beendet den Ladezustand.

Der abgeschnittene Leerraum oberhalb des Gebäudedachs bleibt erhalten. Die drei
vorhandenen reversiblen Migrationen 0024, 0025 und 0027 aus main sind auf der lokalen
Entwicklungsdatenbank angewendet; es wurden keine Migrationen neu erstellt oder
bestehende Migrationen umgeschrieben. Der Merge wird erst mit einem späteren,
vom Nutzer ausgeführten Commit abgeschlossen. GitHub und remote Branches werden
für diese lokale Konfliktlösung nicht verändert.
Prüfung des kombinierten Stands: vollständige Suite mit 653 Tests erfolgreich;
61 Bewerbungs-/Navigationsprüfungen nach der letzten Tabellenkorrektur zusätzlich
erfolgreich. Django-Check, Migrationsprüfung, Ruff-Lint, Ruff-Formatprüfung und
Diff-Prüfung erfolgreich. Browser-Smoke: Bewerbungsübersicht, mobile Filter und
Bewerbungsdetails sowie Übergabeformular ohne JavaScript-Syntaxfehler. Seltene
Datenzustände und Anmeldeseiten sind zusätzlich durch die Django-Tests abgedeckt.
Übergaben und Verwaltung/Bewerbungen verwenden dieselben Containerbreiten und
Seitenabstände. Die Übersichtsüberschrift und die Anlegen-Aktion stehen auf
schmalen Bildschirmen untereinander. Die Übergabe-Bereichsnavigation zeigt auf
der Übersicht nur „Übergaben“; weitere Punkte benötigen ein ausgewähltes
Protokoll, Bearbeitungspunkte zusätzlich dessen offenen Status. Dies hängt auf
der Mitarbeiterübersicht nicht von zusätzlichen Kontorechten ab.
Aktive Bereichslinks behalten ihre feste Linienmarkierung ohne zusätzliche
Textunterstreichung; die Hover-Unterstreichung bleibt auf anderen Links erhalten.

Dasselbe Verhalten gilt für die Desktop-Hauptnavigation im Header: Die aktive
Seite zeigt nur die feste Positionslinie, ohne zusätzliche Textunterstreichung
bei Hover oder Fokus. Der sichtbare Tastatur-Fokusrahmen bleibt erhalten.


## Übernahme der Zustandsmuster – 14. Oktober 2026

Blockierende Abschlussfehler erscheinen vor der Protokollzusammenfassung, mit
Links zum vorhandenen Protokoll und seinen Prüfpunkten. Vollständigkeitsprüfung,
Unterschriftenformular und Freigabe bleiben unverändert. Der allgemeine Rückweg
funktioniert auch für fehlende Zähler-/Schlüsselangaben; Fehlertexte werden nicht
als Grundlage einer neuen fachlichen Zuordnungslogik ausgewertet.

Die vorhandenen Prüf-/Einladungsformulare verwenden die gemeinsamen Feldbausteine.
Feldnamen, Hidden-Felder, CSRF, POST-Ziele und Validierung bleiben bestehen.
Mitarbeiterseiten, Filterbeschriftungen, Benachrichtigungen und Einladungstexte
verwenden „Hauptbewerbung“ bzw. „Bewerbung“. Python-Namen, Statuswerte und geteilte
Migrationen werden nicht umbenannt. Die historische Enum-Beschriftung für
`main_unlocked` wird nur in der Anzeige des Änderungsverlaufs übersetzt; damit
entsteht keine Migration für eine reine UI-Beschriftung.

PDF-Fehler bekommen einen eindeutigen Seitentitel und einen rollenabhängigen
Rückweg. Es wird keine PDF-Erzeugung automatisch erneut ausgelöst. Bewerbungssegmente
sind normale Navigation mit `aria-current`, da der Server neue Ansichten liefert.
Die Befunde und die Grenzen der Nachlade-Rückmeldungen bleiben für die PR dokumentiert.

Prüfstand nach der Übernahme: 111 Browseraufrufe bei 1440, 390 und 320 Pixeln
ohne Seitenüberläufe, fehlende Formularverknüpfungen oder kaputte Bilder. Der
blockierende Abschlussfehler beginnt im geprüften Mobilzustand bei ca. 502 px
statt 3542 px. Die vollständige Suite mit 653 Tests hatte eine überholte
Buttontext-Erwartung („Main-Bewerbung“); nach Anpassung sind die 37 gezielt erneut
geprüften Auswahl-, Zugriffs- und Fehlerseitentests erfolgreich. Die übrigen
Tests der vollständigen Suite waren erfolgreich. Django-, Migrations-, Ruff-
und Diff-Prüfungen sind erfolgreich. Keine Änderung an Schema oder Berechtigungen.
