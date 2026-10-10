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
| `_site_footer.html` | Unternehmensbezeichnung, Navigation und rechtliche Informationen |

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

## Vorschau und offene Punkte

Die Oberfläche wird direkt auf [localhost:8000](http://localhost:8000/) geprüft,
insbesondere [Wohnungssuche](http://localhost:8000/wohnungen/) und
[Anmeldung](http://localhost:8000/accounts/login/). Es gibt keinen separaten
Header-/Footer-Prototyp mehr.

- Das Original-Logo kann später in den gemeinsamen Header eingebunden werden.
- Impressum und Datenschutz sind im Footer verlinkt und als Layoutentwürfe unter
  `/impressum/` und `/datenschutz/` erreichbar. Ihre Platzhalter sind keine fertigen
  Rechtstexte. Das Unternehmen ergänzt und prüft die verbindlichen Angaben vor Veröffentlichung.
- Die Gebäudeansicht verwendet bereits die in #16 vorgesehene Adresse
  `/wohnungen/gebaeude/`. Bis zum Merge beantwortet eine statische Übergangsseite
  in `core.urls` diese Adresse. Die echte Route in `wohnungsverwaltung.public_urls`
  steht in `config.urls` davor und übernimmt nach dem Merge automatisch; die
  Navigation verwendet dann ihren Namen `wohnungsverwaltung_public:building_view`.
  Die Übergangsroute und `core/building_pending.html` können danach entfernt werden.
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
