# Hellblauer Designentwurf

Stand: 15.10.2026. Lokaler experimenteller Entwurf, menschliche Designabnahme ausstehend.

## Auftrag und Ausgangsbasis

Eigenständige helle Wohnungsvermietung für ein Gebäude mit 25 Einheiten. Keine neuen
fachlichen Funktionen, Modelle, Migrationen oder Abhängigkeiten. UIkit 3.25.24 bleibt
lokal und unverändert. Kein Push, PR, Merge, Deployment oder GitHub-Schreibzugriff.

Branch: `test/light-blue-redesign`, ausdrücklich vom Nutzer freigegeben. Am
15.10.2026 `origin/main` abgerufen und den Branch direkt auf
`d79562647af183ac66af4913618c1bc4b4dbb6e1` erstellt; HEAD und Remote-Referenz
waren identisch. Der vorherige lokale main war veraltet. Vorhandene unversionierte
`.gitattributes` und zwei Filter-SVGs bleiben unangetastet. Lokale IDE-Dateien
gehören nicht zum Entwurf.

Gelesen: AGENTS.md, README, Stack-ADR, Theme-ADR und Zugriffs-ADR. Design-Issues
#44–47 sowie Folgeaufgaben #128/#129 ausschließlich lesend recherchiert.

## Referenzvergleich

Offizielle Seiten, Abruf und Browseruntersuchung am 15.10.2026. Auswahl als
Gestaltungsreferenzen, keine Marktführerrangliste. Texte, Bilder, Logos und
Markenfarben wurden nicht übernommen. Namen und Quellen stehen nur hier.

| Referenz | Tatsächlich untersuchte Ansichten | Sichtbarer Befund / Eignung |
|---|---|---|
| [ImmoScout24](https://www.immobilienscout24.de/) | Einstieg; Mietübersicht über „Mietwohnungen“; [Detail](https://www.immobilienscout24.de/expose/168052908) | Große zentrale Suche; Bildkarten und Ergebniszahl, zusätzliche Kartenansicht. Detail mit separater Kalt-/Warmmiete und Kontaktpanel. Suchorientierung geeignet, bundesweite Karte für ein Haus überflüssig. |
| [immowelt](https://www.immowelt.de/) | Einstieg; [Mietübersicht](https://www.immowelt.de/suche/mieten/wohnung/deutschland/ad02de1), auch bei 390 px; [Detail](https://www.immowelt.de/expose/cf896c22-9707-4e90-9c2b-e35bc57ee3ae) | Klare Mietauszeichnung, wiederkehrende Positionen für Fläche/Zimmer/Etage; großflächige Fotos. Mobil kompakte Filteröffnung und gestapelte Karten; App-Werbung überdeckt einen Teil der Liste und wird für STEImmo nicht übernommen. |
| [Engel & Völkers](https://www.engelvoelkers.com/de/de) | Einstieg; [Mietübersicht](https://www.engelvoelkers.com/de/de/immobilien/res/mieten/immobilien); [Detail](https://www.engelvoelkers.com/de/de/exposes/457b4630-5117-5287-9761-6d3ad04485d3) | Viel Weißraum, ruhige Typografie, große Galerie, Mietart ausdrücklich benannt, Kontakt im Objektkontext. Übernommen wird die Ruhe; keine Luxusinszenierung oder automatisch wechselnde Bühne. |
| [Rightmove](https://www.rightmove.co.uk/) | Einstieg; [Mietübersicht](https://www.rightmove.co.uk/property-to-rent/london.html), auch bei 390 px nach Schließen des Cookie-Banners; [Detail](https://www.rightmove.co.uk/properties/92525256) | Kauf/Miete früh getrennt, Suche als Hauptaktion, Kontozugang nachgeordnet. Mobil kompakte Filteröffnung, Bild vor Daten; Detail mit Mietzeitraum, Verfügbarkeit und Kontaktpanel. Für STEImmo genügt ein eindeutiger Vermietungseinstieg. |
| [Zoopla](https://www.zoopla.co.uk/) | Einstieg; [Vermietung](https://www.zoopla.co.uk/to-rent/); [Liste](https://www.zoopla.co.uk/to-rent/flats/london/); [Detail](https://www.zoopla.co.uk/to-rent/details/74276222/) | Horizontale Bild-/Informationskarten, Monatspreis prominent, Filter oberhalb der Ergebnisse; Detail mit separatem Kontaktpanel und explizitem Rückweg. Für vergleichbare Einheiten besonders geeignet. |
| [Savills](https://www.savills.co.uk/) | Einstieg; [Mietsuche](https://search.savills.com/list/property-to-rent/uk?tracking=true&functional=true); [London](https://search.savills.com/list/property-to-rent/england/london); [Detail](https://search.savills.com/property-detail/gbdorecnl260545l) | Großzügige Typografie und Suche; Mietsuche nutzt eine große Gebietskarte. Detail mit großer Galerie, monatlicher Preisangabe und zugeordnetem Ansprechpartner. Objektbezug geeignet, Kartenfläche und weltweite Navigation ungeeignet. |

Die Startseiten wurden im echten Browser visuell untersucht, nicht nur aus
Suchmaschinenausschnitten abgeleitet. Cookie-Banner und verzögert geladene Inhalte
erschwerten einzelne Ansichten. Ein Klick kann in einem neuen Tab öffnen; eine
noch sichtbare Ergebnisliste zählt deshalb nicht als geprüfte Detailseite.

### Konkrete Entscheidungen

| Beobachtetes Muster | Nutzen | Anpassung an STEImmo |
|---|---|---|
| Suche steht früh im Einstieg (Portale) | Nächste Handlung sofort klar | Kompakter geteilter Einstieg mit direkter Wohnungssuche und tatsächlicher Verfügbarkeitszahl. Keine Ortssuche für weitere Immobilien. |
| Einheitliche Bild-/Datenpositionen (Mietlisten) | Wohnungen schneller vergleichbar | Horizontale Angebotszeilen auf Desktop, gestapelte Karten mobil; Fläche/Zimmer und Kaltmiete mit festen Positionen. |
| Mietart und Zeitraum beim Preis (Listen/Details) | Kosten werden korrekt eingeordnet | „Kaltmiete / Monat“ bleibt ausdrücklich erhalten; Warmmiete und Kaution separat, fehlende Werte ehrlich benannt. |
| Objektbezogenes Kontaktpanel (Details) | Kontakt bleibt der Wohnung zugeordnet | Mietpanel neben Galerie und Inhalt; mobil vor der längeren Beschreibung, ohne fixierte Überlagerung. |
| Ruhige Maklertypografie und Weißraum | Inhalte sind leichter zu erfassen | Dunkelblaue Schrift auf Weiß und Hellblau, kurze Zeilen, abgestufte Überschriften, lokale Systemschriften. |
| Sichtbarer Suchkontext (Portale) | Filterwirkung nachvollziehbar | Vorhandene GET-Filter behalten ihre Werte; zusätzliche Zusammenfassung aktiver Werte mit Reset-Link. |
| Schrittweise Vermietungsorientierung | Interessenten verstehen den Ablauf | Bestehende Folge Suche → Detail → Konto → Besichtigungsanfrage → Freigabe → Nachweise bleibt sichtbar. Keine sofortige Terminzusage. |
| Bilder und transparente Angaben schaffen Vertrauen | Keine falschen Erwartungen | Vorhandenes Stadtfoto klar als Würzburg beschriftet; keine erfundenen Objektfotos. Fehlende Galerie als ein kompakter Zustand statt drei leerer Bildflächen. |

Betrachtet wurden Navigation, Suchgewichtung, Eckdaten, Bilder/Zuschnitt,
Angebotskarten, Detailhierarchie, Kontaktposition, Typografie/Weißraum/Kontrast,
mobile Bedienbarkeit und Vertrauen. Mobile Referenzbefunde werden nur für
tatsächlich geprüfte schmale Ansichten beansprucht; keine vollständige
Barrierefreiheitsprüfung der fremden Angebote.

## Gestaltungsrichtungen

- **Licht & Architektur (gewählt):** Weiß/Hellblau, klare Systemtypografie,
  geteilter Einstieg, kompakte Angebotszeilen und vorhandene Gebäudezeichnungen.
  Hohe Klarheit, ruhige Wohnlichkeit und eigene Identität; passt zum Vergleich
  von 25 Einheiten in einem Haus.
- **Wohnjournal:** große atmosphärische Fotobühne und stärker redaktionelle
  Überschriften. Wohnlicher, aber weniger direkter Angebotszugang und abhängig
  von ausreichend guten Objektbildern. Für den vorhandenen Bestand schwächer.

Gemeinsame Tokens und Theme-Regeln liegen in `static/css/app.css`, der Rahmen
in den vorhandenen Partials. Semantische Statusfarben bleiben von Markenblau
getrennt und werden durch Text ergänzt. Fokus erhält einen sichtbaren Ring.

## Seiteninventar und Umfang

Alle folgenden Seiten existieren auf der geprüften Basis und nutzen denselben
Rahmen sowie die gemeinsamen Formular-, Status-, Tabellen- und Kartentokens:

| Bereich | Vorhandene Seiten / Zustände | Redesign |
|---|---|---|
| Öffentlich | Start, Wohnungssuche, aktive/ungültige Filter, leere Ergebnisse | Neuer Einstieg, Angebotszeilen, Filterpanel und aktive Auswahl |
| Objekt | Gebäude, fünf Etagenansichten, verfügbare Wohnungsdetails, Galerie/Lightbox, fehlende Bilder | Gebäude und Etagenwahl nebeneinander; Details mit früherem Mietpanel |
| Kontozugang | Anmeldung, Registrierung, Bestätigungscode, Mitarbeiter-MFA, Feld-/allgemeine Fehler | Gemeinsamer heller Formularrahmen; vorhandenes Symbolbild bleibt als solches gekennzeichnet |
| Bewerber | Anfrage, Übersicht, Hauptbewerbung/Uploads, eingereichter Zustand, Rückzug, Terminantworten, gesperrter Anfragezustand | Gemeinsamer Rahmen, Fortschritt, Formular- und Statusgestaltung |
| Verwaltung | Wohnungen und Räume, Fotos, Stellplätze, Merkmale, Benutzer; Listen und Formulare | Helle Tabellen/Flächen, einheitliche Navigation und Aktionen |
| Mitarbeiter | Bewerbungsübersicht/-detail, Prüfung, Termine | Gemeinsames Theme, Statusfarben und Formulare |
| Übergaben/Mieter | Liste, eigene Protokolle, Anlage/Bearbeitung, Räume, Schlüssel, Abschluss/Unterschrift, Exportfehler | Gemeinsames Theme; bestehende Foto- und Signaturbedienung erhalten |
| Information | Impressum, Datenschutz, Bildnachweise, Fehlerseite | Gemeinsamer heller Rahmen |

Nicht neu gebaut: Suchfunktionen in Verwaltungslisten (#128), persönliche
Profilbearbeitung (#129), Passwort-Reset, öffentliche Bewertungen oder weitere
Immobilien. Rechtliche Entwurfshinweise und fehlende Anbieterangaben sind
vorhandene Inhalte; sie werden nicht durch erfundene Angaben ersetzt.
Standard-Django-Admin und PDF-Dokumentgestaltung sind nicht Teil des Entwurfs.

## Meilensteine und Iterationen

- [x] G1: Basis/Regeln/Seiteninventar geprüft; Anwendung vor Änderungen im Browser gesehen.
- [x] G2: Drei deutsche und drei englischsprachige Anbieter visuell verglichen; acht Entscheidungen abgeleitet.
- [x] G3: Gemeinsames Theme, Einstieg, Suche, Details und Gebäudeaufbau umgesetzt.
- [x] G4: Alle vorhandenen Seitengruppen auf Konsistenz geprüft; 30 unterschiedliche Seiten in der Browsermatrix.
- [x] G5: Browserwege, fünf Breiten, Rollen, Uploads, Datum und Qualitätsgates geprüft (Nachweise unten).
- [x] G6: Vollständigen Produktdiff und Bericht geprüft; lokale, uncommittete Übergabe vorbereitet.

**Runde 1:** Einstieg verkürzt und geteilt, Angebotszeilen und Filterpanel,
gemeinsame helle Navigation/Formulare/Tabellen. Desktopprüfung zeigte zu große
Leerfläche bei fehlenden Detailfotos und späte mobile Kontaktaktion.

**Runde 2:** Fehlende Galerie auf einen kompakten Zustand reduziert; Mietpanel
mobil vor längere Beschreibung gesetzt. Anfrage mit Pflichtfeldfehlern und
erfolgreicher Übermittlung auf 390 px geprüft. Kombinierte Fläche-/Miet-/Zimmer-/
Etagenfilter liefern die erwarteten drei synthetischen Wohnungen; Auswahl und
Reset sind sichtbar.

**Runde 3 / Gesamtdurchsicht:** 30 zentrale Ansichten (sechs Seiten × fünf
Breiten) sowie 48 weitere Ansichten (24 Seiten × zwei Breiten) im Browser
geöffnet und per DOM auf Titel und horizontalen Seitenüberlauf geprüft.
Screenshots von zentralen Desktop-, Tablet- und Mobilansichten visuell geprüft.
Bei einer langen synthetischen Wohnungsbezeichnung war der Titel zunächst
833 px breit innerhalb einer 344-px-Karte und wurde abgeschnitten. Nach
`overflow-wrap: anywhere` und begrenztem Flex-Inhalt ist er 312 px breit und
vollständig mehrzeilig sichtbar. Anschließend Fehlertext-Einzug im schmalen
Filterfeld reduziert. Überflüssige eigene Hero-Regeln entfernt und doppelte
Theme-Deklarationen zusammengeführt. Betroffene Suche und Details erneut geprüft.

## Prüfumgebung und Nachweise

Die bestehende lokale Anwendung läuft auf Port 8000. Für schreibende Prüfungen
wurde ausschließlich `steimmo-redesign` mit eigener Datenbank
`steimmo_redesign`, flüchtigem Media-Verzeichnis und Django-Locmem-Mailbackend
gestartet, aktuell erreichbar unter **`http://localhost:57651/`**. Kein externer Mailversand. Der feste Port
8010 war belegt; Docker hat deshalb einen freien lokalen Port zugewiesen.
Vor dem Template-Neustart war dies Port 49684; die früheren Screenshots stammen
von dort. Nach dem Neustart änderte Docker den dynamischen Port. Die flüchtigen
Testdateien wurden ausschließlich aus der synthetischen Testdatei wiederhergestellt.
Die neue Datenbank wurde mit vorhandenen fiktiven Standarddaten und ausdrücklich
synthetischen Mieten/Zimmerzahlen/Testkonten befüllt. Testwerte sind keine
Behauptungen über reale Wohnungen. Keine Fixture-Änderung im Produktrepository.

Screenshots/Testdateien liegen außerhalb des Repositorys unter
`C:/Users/timog/.codex/visualizations/2026/10/15/01a13f3a-eef1-7422-beaa-ffe2986beca0/`.
`before-home.jpg` und `before-search.jpg` dokumentieren die alte Gestaltung;
`after-*.jpg` die jeweils benannten Prüfzustände. Native sichtbare Seitenleisten
haben andere Abmessungen; für feste Breiten wird die verborgene Browser-Vorschau
verwendet und die tatsächliche `innerWidth` kontrolliert.

### Browserergebnisse

| Prüfung | Ergebnis |
|---|---|
| 360, 390, 768, 1280, 1440 px | Einstieg, Suche, Detail, Gebäude, Etage und Wohnungsliste geöffnet; tatsächliche `innerWidth` entspricht jeweils der Sollbreite. `scrollWidth == clientWidth` in allen 30 Fällen. |
| Weitere Seiten bei 390/1440 px | Wohnungs-/Raum-/Fotoverwaltung, Stellplätze, Prüfvorlagen, Benutzerkonten, Mitarbeiterbewerbungen, Übergaben einschließlich Raum/Schlüssel/Abschluss, Kontozugang und Information: alle 48 Aufrufe mit zutreffendem h1, kein horizontaler Seitenüberlauf. Lokales Scrollen im großen Grundriss und in komplexen Zählertabellen bleibt bewusst erhalten. |
| Suche | Einzelner Etagenfilter, kombinierte Fläche/Miete/Zimmer/Etage, Werteerhalt, drei erwartete Treffer, Reset auf 16 Treffer; ungültiger negativer Wert mit Feld- und allgemeinem Fehler; leere Ergebnisse und vollständig belegter Testbestand. Testbestand danach wiederhergestellt. |
| Detail/Galerie | Normale Detailseite, fehlende Bilder, vier ausdrücklich als synthetisch bezeichnete Testbilder, Lightbox öffnen, nächstes Bild und Escape. Kosten/Anfrage liegen mobil vor der Beschreibung. |
| Konto/Anfrage | Fehlerhafte Anmeldung mit erhaltenem Benutzernamen; gültige Anmeldung kehrt zur gewählten Wohnung zurück. Anfrage zunächst mit Pflichtfeldfehlern, dann auf 390 px erfolgreich abgesendet. |
| Hauptbewerbung | Synthetischer Datensatz für Uploadprüfung gezielt freigeschaltet. Textdatei wird abgewiesen; drei gültige Test-PNGs als Entwurf gespeichert und auf Desktop endgültig eingereicht. Danach Erfolgsnachricht, 3/3 Nachweise und unveränderliche eingereichte Ansicht. Freigabe ist Testvorbereitung, kein Nachweis einer tatsächlich erfolgten Besichtigung. |
| Rollen | Bewerber erhält 403 auf Verwaltung. Benutzerverwalter über Passwort und deterministischen lokalen MFA-Testcode angemeldet, Verwaltungsseiten geprüft. Synthetischer Mieter sieht sein zugeordnetes bestätigtes Altprotokoll. Keine Änderungen an produktiven Berechtigungen oder Authentifizierungslogik. |
| Datum/Tastatur | Vorhandene `date`- und `datetime-local`-Felder im Übergabeformular kontrolliert; Datum 30.10.2026 im Browser eingegeben und ohne Speichern verworfen. Mobilmenü per Enter geöffnet, mit Escape geschlossen; aktiver Link mit sichtbarem blauem Fokusring. |

Die visuellen Stichproben umfassen u. a. `after-home-1440.jpg`,
`after-home-768.jpg`, `after-search-768.jpg`, `after-detail-1280.jpg`,
`after-building-360.jpg`, `after-building-1440.jpg`, `after-floor-360.jpg`,
`after-management-360.jpg`, `after-mobile-menu-390.jpg`,
`after-employee-detail-390.jpg`, `after-tenant-390.jpg`,
`after-long-title-390.jpg` sowie die benannten Fehler-/Erfolgszustände.
Die JSON-Matrizen liegen daneben. Die Matrixmessung ersetzt keine visuelle
Stichprobe; beide wurden durchgeführt. Ganzseitige Screenshot-Exporte waren
mit diesem Browser nicht verfügbar, daher wurden sichtbare Ausschnitte und
gezielt angesteuerte tiefere Seitenbereiche festgehalten.

### Kontraste und Qualitätsgates

Berechnung nach relativer sRGB-Luminanz: Text auf Weiß 13,78:1; Text auf Hellblau
11,84:1; Sekundärtext auf Hellblau 5,05:1; Weiß auf Aktionsblau 7,07:1;
Fokusring auf Hellblau 4,65:1; Eingaberand auf Weiß 3,63:1.

- Vollständige vorhandene Django-Suite: **691 Tests erfolgreich**, 255,345 s.
- Abschließend gezielte Core-/Response-/UI-Tests: **231 Tests erfolgreich**, 102,727 s.
- `python manage.py check`: erfolgreich, keine Probleme.
- `python manage.py makemigrations --check --dry-run`: keine Änderungen.
- `ruff check .`: erfolgreich.
- `ruff format --check .`: 127 Dateien bereits formatiert.
- `git diff --check`: erfolgreich, nach Beseitigung einer Leerzeile mit Leerzeichen.
- Vollständiger Diff und Status geprüft: ausschließlich Theme, vorhandene
  Templates und dieser Bericht; keine Vendor-, Python-, Modell-, Migrations-,
  Dependency- oder AGENTS-/README-Änderung. Keine Testmedien oder Konten versioniert.

Erwartete Meldungen aus simulierten Speicher-/Mailfehlern der Testsuite sind
erfolgreich geprüfte Fehlerfälle. Zwischenzeitliche Browserprobleme durch den
Portwechsel wurden durch Neuverbinden gelöst; diese gelten nicht als bestandene
Aufrufe und sind nicht in den erfolgreichen Matrizen enthalten.

## Übergabe und Grenzen

Das native Haupt-Goal wird für die vereinbarte **lokale Übergabe** abgeschlossen,
nicht für die vollständige Repository-Definition-of-Done mit Review und Merge.
Die Änderungen sind lokal und uncommittet auf dem beauftragten Branch.
Keine GitHub-Änderungen gemäß Auftrag.

Offen bleibt die menschliche Designabnahme. Produktive Objektbilder, Preis- und
Kontaktdaten sowie rechtliche Entwurfstexte benötigen weiterhin die dafür
zuständige fachliche Pflege; synthetische Prüfdaten ersetzen diese nicht.
Keine vollständige Screenreader-/Geräte- oder Browserkompatibilitätsprüfung.
PDF-Erzeugung und verbindlicher Protokollabschluss wurden nicht als Teil des
Redesigns neu ausgeführt; die bestehende Testsuite deckt ihre fachlichen Regeln ab.
Filterkontext wird in den GET-Formularen erhalten; der Detail-Rückweg führt wie
zuvor zur ungefilterten Übersicht. Eine Erweiterung dieses Verhaltens wurde nicht
in den Gestaltungsauftrag aufgenommen.

Die isolierte Vorschau und Datenbank bleiben zur Abnahme vorhanden. Das
Media-Verzeichnis ist flüchtig und benötigt nach einem Containerneustart erneut
synthetische Testdateien. Für den regulären Start gilt unverändert die README.
