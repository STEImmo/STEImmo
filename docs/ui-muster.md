# Gemeinsamer Seitenrahmen – US-18

## Grundlage und Abgrenzung

[US-17 / #45](https://github.com/STEImmo/STEImmo/issues/45) liefert das Corporate-Theme
und wurde mit [PR #72](https://github.com/STEImmo/STEImmo/pull/72) integriert:
Farben, Typografie, Abstände, Radien, Schatten und Zustände liegen zentral in
`static/css/app.css`. Das [Theme-ADR](decisions/0008-uikit-theme-design-token-architecture.md)
beschreibt diese Grundlage. Die Tokens und die lokalen UIkit-Assets bleiben bestehen.

[US-18 / #46](https://github.com/STEImmo/STEImmo/issues/46) ergänzt gemeinsame
UI/UX-Muster auf den echten Django-Seiten. Der erste Schritt umfasst Header,
mobile Navigation, Footer und die sichtbare Unternehmensbezeichnung.
Weitere Formular-, Listen- und Seitenmuster sind noch offen.

## Noch offener Umfang von US-18

Der Seitenrahmen ist ein Teil der Story. Die geplanten 6–8 Stunden gelten für
die gesamte Umsetzung einschließlich der Prüfung; sie sind keine gemessene
Arbeitszeit und keine Zusage für ein vollständiges Redesign aller Seiten.
Für die restliche Umsetzung gelten folgende konkrete Arbeitspakete:

- Gemeinsamer Seitenkopf mit Seitentitel, Erklärung, Hauptaktion und Rückweg;
  auf öffentlichen und internen Seiten einsetzen. Die bestehende Palette aus
  US-17 auch in Inhaltsbereichen erkennbar anwenden.
- Formularmuster für sichtbare Labels, Pflichtfelder, Hilfen, feldnahe Fehler
  sowie Speichern und Abbrechen; Anmeldung, Registrierung, Bewerbung und
  Verwaltungsformulare auf dieses Muster bringen.
- Bewerberübersicht und Hauptbewerbung mit verständlichen Abschnitten,
  Bearbeitungsstand und nächster Handlung gestalten; Besichtigungsanfrage,
  Freigabe und Einreichung bleiben fachlich unverändert.
- Wohnungs- und Bewerbungslisten sowie Mitarbeiterdetails vereinheitlichen;
  Tabellen, Karten, Filter und Aktionen auch auf kleinen Bildschirmen bedienen können.
- Gemeinsame Muster für leere Listen, Erfolg, Warnungen, Fehler und tatsächlich
  vorhandene Upload-/Ladezustände anwenden. Keine künstlichen Ladeanimationen ergänzen.
- Relevante Seiten und Zustände mit den vorhandenen Rollen prüfen; Browser,
  Tastatur, Mobilansicht, Response-Tests, Dokumentation und unabhängiges Review abschließen.

Die nächste vollständige Umsetzung umfasst **Meine Bewerbungen → Bewerbung
erstellen → Hauptbewerbung vervollständigen**, einschließlich leerer Liste,
offener Bewerbung, Freigabe, Einreichung, Fehlern und Rückwegen. Das dort
erprobte Seiten-, Formular- und Statusmuster wird anschließend auf die übrigen
relevanten Seiten übertragen.

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
und Gebäudeansicht. Die technische Bewerbungsvorschau ist kein Navigationspunkt;
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
| Alle: Kontaktangaben | Footer → Kontaktabschnitt des Impressums | 1 |
| Gäste: Etage | Gebäudeansicht → Stockwerk | 2 |
| Gäste: Wohnungsdetails | Wohnungssuche → Details; alternativ Gebäude → Etage → Wohnung | 2–3 |
| Gäste / Bewerber: Besichtigungsanfrage | Wohnungssuche → Details → Zur Besichtigung anmelden | 3 |
| Bewerber: neue Bewerbung | Meine Bewerbungen → Neue Bewerbung, sofern keine offene Bewerbung besteht | 2 |
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
