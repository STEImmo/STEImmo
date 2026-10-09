# Gebäude- und Wohnungsansicht (US-02, #16)

Der Prototyp läuft in der bestehenden Django-Anwendung über Docker. Einstieg: http://localhost:8000/wohnungen/gebaeude/ oder „Gebäude erkunden“ im Header.

## Seiten und Grundrisse

Der Rückweg „Zur Gebäudeansicht“ steht neben der Geschossauswahl und bleibt beim Ankereinstieg sichtbar. Auf schmalen Bildschirmen bricht die Navigationszeile um. Der Hinweis zur vorläufigen Position entfällt auch auf der Wohnungsdetailseite; die dokumentierten Grenzen der Zuordnung bleiben bestehen.

DG: Die möglichen Dachflächenfenster aus den rot gestrichelten Rechtecken der Vorlage werden auf Nutzerwunsch weggelassen. Ihre Interpretation ist unbestätigt; der vereinfachte Auswahlplan bleibt ohne diese Symbole und ohne erfundene Außenfenster.

Nicht verfügbare Wohnungen erscheinen im Grundriss als graue, diagonal schraffierte Flächen mit dem Hinweis „Nicht verfügbar“, ohne sichtbare Nummern-/Flächenschilder. Ihre zugänglichen Statusbeschreibungen bleiben erhalten. Die Verfügbarkeitslegende unter dem Plan entfällt auf Nutzerwunsch.

1. Gebäudeansicht mit vereinfachter Westfassade und auswählbaren Stockwerken. Auf Nutzerwunsch ist die ursprüngliche Straßenseite mit zwei Gauben und drei Balkonachsen wiederhergestellt; die zuvor erfundene EG-Eingangstür entfällt. Eine Auswahl direkt an der Fassade; Wohnungs- und Verfügbarkeitszahlen stehen auf den Stockwerksschildern. Keine zweite Auswahlliste daneben. Dekorative Bäume liegen außerhalb der Beschriftungen und fangen keine Klicks ab.
2. Eigene Etagenansicht mit einem vereinfachten SVG-Vektorgrundriss, freien anklickbaren und nicht verfügbaren ausgegrauten Wohnungen. Die Wohnungsliste ergänzt die grafische Auswahl. Links von der Fassade, aus den Wohnungsdetails und zwischen den Etagen führen auf Nutzerwunsch wieder direkt zur Geschossauswahl über dem Grundriss. Der Anker hat 18 Pixel Abstand zum oberen Rand. Der normale Header ist wiederhergestellt, ohne Sticky-Verhalten oder zusätzlichen JavaScript-Code.
3. Wohnungsdetails mit gespeicherten Werten, Fotogalerie und „Zur Besichtigung anmelden“.

Die Gebäudeseite nutzt ab Desktopbreite ein UIkit-Grid mit 2/3 Fassade links und 1/3 Hausüberblick rechts. Der Überblick zeigt Wohnungszahl, vorhandene Etagen und aktuell verfügbare Wohnungen aus derselben Datenbankauswertung wie die Fassadenschilder. Auswahlhilfe und Link zur Suche ergänzen ihn. Auf kleineren Bildschirmen stehen beide Bereiche untereinander. Es gibt weiterhin keine zweite Stockwerksauswahl.

Die einzelnen Fassadenfenster liegen mittig in ihrer Einfassung. Die seitlichen Laibungen haben gleiche Breite und gespiegelte Konturen; obere und untere Kanten verlaufen parallel. Die vereinfachten Fenster erhalten wie in der Westansicht eine ungeteilte Glasfläche.

Die Vektorgrafiken orientieren sich an den gelieferten Zeichnungen. Für das EG dient die vereinfachte Nutzerskizze als Grundlage für Wandaufteilung und Proportionen. Die Geometrie ist auf gemeinsame horizontale und vertikale Achsen ausgerichtet; lediglich die tatsächliche schräge rechte Außenkante bleibt erhalten. Die ruhige bestehende Farbgebung mit hellen Fensterlinien, dezenten Türbögen und Balkonflächen wird weiterverwendet. Balkone, Treppe, Aufzug, Flur und Fahrradabstellbereich sind schematisch dargestellt und beschriftet. Der Aufzug liegt am rechten Flurende unterhalb des Fahrradbereichs, mit Zugang vom Flur auf der linken Schachtseite. Möbelsymbole, Fahrradständersymbole und der Außenstellplatz sind im EG auf Nutzerwunsch entfernt. Auch das DG verwendet die horizontale Orientierung und den bereinigten Zeichenstil. Seine Geometrie folgt der beschrifteten Nutzerskizze und der Architekturvorlage: Wohnung 402 links, 401 rechts, drei Balkonabschnitte und eine Trennwand zwischen den beiden unteren Balkonabschnitten. Die Anwendung verwendet ausschließlich die nachgebauten SVG-Zeichnungen. Der Link zu den Originalplänen und die drei Originalplan-PNGs wurden auf Nutzerwunsch aus dem Projekt entfernt.

Die Darstellung ist nicht maßstabsgetreu. Die Wohnungsnummern sind den Flächen vorläufig zugeordnet und müssen fachlich bestätigt werden. Die drei Obergeschosse verwenden denselben Grundrisstyp. UIkit 3.25.24 bleibt die Komponentenbasis; es gibt keine zusätzliche Bibliothek oder eigenständige HTML-Vorschau.

Die vorläufige EG-Zuordnung folgt der Nachrechnung des Nutzers: Wohnung 1 oben mittig, Wohnung 2 rechts unter dem Fahrradbereich, Wohnung 3 unten mittig, Wohnung 4 unten links und Wohnung 5 oben links. Dies ist keine bestätigte Lageangabe. Die Wohnungsnummern und Wohnflächen in der Datenbank bleiben unverändert; lediglich ihre Positionen in der Zeichnung werden zugeordnet.

Das 1., 2. und 3. OG verwenden einen gemeinsamen bereinigten Vektorplan im EG-Zeichenstil: sechs Wohnungen, eine Wohnung im Bereich des EG-Fahrradraums, drei kleinere Balkone an der oberen Seite und drei weitere Balkone. Wände, Raumgrenzen und Türöffnungen folgen der neuen Nutzerskizze für das 1. und 2. OG. Im 3. OG haben die oberen Balkone nach der zusätzlich gelieferten Skizze schmalere Flächen und seitliche Rundungen; die innere Aufteilung bleibt gleich. Möbel entfallen. Die Treppe zeigt zwei getrennte Läufe mit entgegengesetzten Pfeilen und einem gemeinsamen Podest; der Aufzug bleibt am rechten Flurende. Die OG-Nummerierung folgt der beschrifteten Nutzerskizze im Uhrzeigersinn: 1 oben mittig, 2 oben rechts, 3 unten rechts, 4 unten mittig, 5 unten links, 6 oben links (jeweils mit Etagenpräfix 1, 2 oder 3). Die Balkontüren im EG und in den drei OG haben einheitliche schematische Breite von 33 Zeichnungseinheiten; Wandöffnungen und Türbögen sind darauf abgestimmt. Die Wohnflächen stammen unverändert aus den jeweiligen Datenbankeinträgen. Die DG-Zeichnung liegt in `_attic_floor_architecture.html`; `ATTIC_SHAPES` ordnet die beiden Auswahlflächen zu. Die Datei `_regular_floor_architecture.html` enthält die gemeinsame Zeichnung für alle drei Obergeschosse; `REGULAR_SHAPES` enthält deren Auswahlflächen.

Die Doppelbögen an den DG-Balkonen werden als zweiflügelige Balkontüren dargestellt. Die zuvor angenommenen Außenfenster im DG sind entfernt. Die möglichen Dachflächenfenster werden für eine ruhigere Darstellung weggelassen; Art und genaue Position sind nicht bestätigt. Aus zwei Öffnungsbögen allein lässt sich die Bauart nicht sicher bestimmen. Diese Darstellung enthält keine verifizierte Bauteilliste.

## Wohnungsdaten

Die EG-Nummern 1–5 werden in den öffentlichen Ansichten und der Fotopflege einheitlich als 001–005 angezeigt. `Wohnung.display_number` formatiert nur diese EG-Nummern; gespeicherte Nummern, UUIDs und Verknüpfungen bleiben unverändert. Die Obergeschosse behalten 101–106, 201–206, 301–306 beziehungsweise 401–402.

Auftraggeberentscheidung laut Nutzer: Barrierefreiheit entfällt in der öffentlichen Ansicht. Heizungstyp und Ausstattung dürfen vorerst leer beziehungsweise als Platzhalter bleiben. Die kleinen Fassadenfenster einschließlich Laibung sind auf Nutzerwunsch mittig um 15 % in Breite und Höhe verkleinert.

Letzter Anschlussabgleich: OG-Beschriftung für Wohnung 3 mittig zwischen den Raumwänden platziert. Balkonlinien im EG und den OG enden direkt an der Fassade; kleine unbeabsichtigte Außenwandlücken sind geschlossen. Wandanschlüsse an der schrägen rechten Außenkante sind auf die tatsächliche Kante verlängert. Der Türbogen des rechten OG-Bads liegt in dessen Öffnung an der Außenkante. Der Hinweis zur vorläufigen Zuordnung entfällt auf Nutzerwunsch in den Etagenansichten; der Hinweis zur nicht maßstabsgetreuen Darstellung bleibt bestehen. Die dokumentierten Grenzen der Quellen bleiben davon unberührt.

Die vom Nutzer gelieferte Liste ist in wohnungsverwaltung/building_plans.py hinterlegt:

- EG: 1–5, fünf Wohnungen
- 1. OG: 101–106, sechs Wohnungen
- 2. OG: 201–206, sechs Wohnungen
- 3. OG: 301–306, sechs Wohnungen
- DG: 401–402, zwei Wohnungen

Nummern, Etagen und Flächen wurden in der lokalen Entwicklungsdatenbank abgeglichen. IDs und Fremdschlüssel bleiben erhalten. Mieten, Zimmerzahlen und Status stammen weiterhin aus den vorhandenen Beispieldaten; die neue Wohnungsliste bestätigt diese Werte nicht.

Wohnfläche, Zimmer, Mieten, Kaution, Status und Fotos sind im System hinterlegt beziehungsweise pflegbar. Beschreibung, Ausstattung, Heizungstyp, Energieausweis, Einzugsdatum, Lagebeschreibung, Kostenaufschlüsselung und Stellplatzzuordnung haben im aktuellen Wohnungsmodell keine entsprechenden Felder. Die Detailseite fasst diese offenen Informationen in kurzen Hinweisen zusammen; sie werden nicht aus den Architekturzeichnungen erfunden. Das Barrierefreiheitskriterium in #16 ist weiterhin mit #53 abzugleichen.

Auf anderen lokalen Datenbanken mit dem ursprünglichen Satz von genau 25 Beispielwohnungen ist der Abgleich explizit auszuführen:

```text
docker compose --env-file docker/.env -f docker/compose.yaml -f docker/compose.dev.yaml exec web python manage.py sync_building_inventory
```

Ohne Option erfolgt nur eine Prüfung. --apply übernimmt Nummern, Etagen und Flächen. Der Befehl verweigert die Ausführung außerhalb von DEBUG sowie bei anderen oder gemischten Wohnungssätzen. Neue Standarddaten verwenden die bestätigte Verteilung. Vor erneutem Seeden eines alten Wohnungssatzes ist der Abgleich erforderlich. Der Abgleich ist keine Schema-Migration und wird nicht automatisch auf fremden Datenbanken ausgeführt.

## Besichtigungsanfrage

Der Button auf der Detailseite führt über einen wohnungsbezogenen Einstieg zur bestehenden Voranfrage. Ohne Anmeldung wird die Zielwohnung über den Login erhalten. Mit Bewerberzugang und Personenprofil öffnet sich das Formular für diese Wohnung. Mitarbeiterkonten ohne Bewerberzugang und Bewerberkonten ohne Personenprofil erhalten eine verständliche Hinweisseite. Die geschützten Bewerbungsseiten behalten ihre Berechtigungsprüfung. Es werden keine Rollen oder Profile automatisch ergänzt. Formular und Erfolgsnachricht sprechen von einer Besichtigungsanfrage. Ein Besichtigungstermin wird separat bestätigt; die Anfrage bucht keinen Termin.

Intern bleibt dies eine Pre-Bewerbung im vorhandenen Bewerbung-Modell. Es wird kein zweiter Bewerbungsablauf eingeführt. Die Hauptbewerbung bleibt gesperrt, bis Mitarbeiter sie nach Besichtigung und positiver Eignungsentscheidung freigeben. Der neue Test prüft Wohnungszuordnung, erfolgreiche Anfrage und weiterhin gesperrten Hauptbewerbungszugang.

Der derzeit auf GitHub definierte Ablauf ist Konto → Pre-Bewerbung → Vorauswahl → Besichtigung → Hauptbewerbung: US-04 (#18) verlangt ein angemeldetes Bewerberkonto. US-13 (#32) ordnet Besichtigungstermine einer Bewerbung zu und zeigt sie im geschützten Bewerberbereich. Der Nutzer bevorzugt möglicherweise eine erste Besichtigungsanfrage ohne Konto; das ist noch nicht entschieden und hier nicht implementiert. Eine solche Anfrage ist nicht mit der bestehenden Pre-Bewerbung gleichzusetzen. Der Buttonhinweis benennt deshalb Konto und Vorauswahl ausdrücklich.

## Wohnungsfotos

Berechtigte Mitarbeiter können unter Verwaltung → Wohnung bearbeiten → Wohnungsfotos verwalten Bilder hinzufügen und entfernen. Migration 0020_apartment_photos ergänzt eine eigene Tabelle. Übergabe- und Bewerbungsdokumente werden nicht als öffentliche Wohnungsbilder verwendet.

- JPEG, PNG und WebP; maximal 8 MiB und 25 Megapixel je Bild, höchstens zwölf Fotos je Wohnung.
- Prüfung des Bildinhalts, Neucodierung als JPEG, maximal 2400 Pixel Kantenlänge, entfernte Metadaten.
- Erstes Foto als Titelbild; UIkit Lightbox für die Galerie.
- Öffentlich ausgelieferte Fotos nur für verfügbare Wohnungen; Mitarbeiter können auch andere Wohnungsfotos verwalten.
- Speicherung in MEDIA_ROOT außerhalb der Versionskontrolle; keine Freigabe des gesamten Medienverzeichnisses.
- Ohne hochgeladene Fotos bleiben neutrale Platzhalter sichtbar.
- Vier KI-generierte Beispieldateien liegen auf ausdrücklichen Nutzerwunsch unter `docs/demo-photos/`. Die dortige README beschreibt das Hochladen über die Verwaltung auf einer anderen Entwicklungsumgebung. Die aktuelle lokale Wohnung 001 enthält sie bereits. Der Commit der Beispiele importiert sie nicht automatisch in die Datenbank; echte Uploads bleiben außerhalb von Git.
- Die Detailseite zeigt höchstens drei Fotos. Weitere Bilder werden durch einen Stapelhinweis „+N Fotos“ auf dem dritten Bild angekündigt und bleiben in der UIkit-Lightbox erreichbar. Ein Klick auf ein Foto öffnet es direkt, ohne zusätzlichen Detailbutton. Das Uploadlimit bleibt bei zwölf. Ein interaktiver 360°-Rundgang ist nicht implementiert und nicht Bestandteil von US-02; ein Panoramabild würde derzeit als normales Foto angezeigt.
- Die Fotoverweise kennzeichnen den Bildtyp ausdrücklich, da die geschützten Auslieferungsadressen keine Dateiendung besitzen. Ein kleines Vanilla-JavaScript ergänzt die normale UIkit-Aufräumroutine, falls beim schnellen Schließen während einer Lade-/Einblendanimation das `hidden`-Ereignis ausbleibt. Damit wird die Scrollsperre zuverlässig aufgehoben; die lokale UIkit-Version bleibt unverändert.

## Prüfung und offene Punkte

Nach der Galerie-Korrektur: 24 relevante Django-Tests, Systemcheck, Migrationsprüfung, Ruff und Formatprüfung erfolgreich. Im Browser geprüft: drei sichtbare Fotos auf Desktop und Mobilgeräten, Stapelhinweis auf dem dritten Foto, geladene vergrößerte Bilder und Zugriff auf das vierte Foto. Nach normalem und sofortigem Schließen ist die Lightbox entfernt und die Seite wieder scrollbar. Die GitHub-User-Story wurde in dieser Runde nicht verändert.

Vor der letzten Galerie-Korrektur: 219 Django-Tests erfolgreich, einschließlich Galerie mit mehr als drei Fotos. Vier mit Imagegen erzeugte Demo-Fotos (Wohnbereich, Küche, Schlafzimmer, Bad) sind in der lokalen Fotopflege von Wohnung 001 hinterlegt und als „Demo – KI-Beispiel“ beschriftet. Vergrößern und Weiterblättern in der UIkit-Lightbox wurden nach der Galerie-Korrektur im Browser erfolgreich geprüft. Die Arbeitskopien im Medienbereich gehören nicht in Git; die ausdrücklich freigegebenen Beispieldateien unter `docs/demo-photos/` dürfen mitcommitted werden. Sie zeigen nicht die tatsächliche Immobilie. Barrierefreiheit entfällt nach Auftraggeberentscheidung; Heizung/Ausstattung dürfen laut Nutzer vorerst Platzhalter bleiben. Letzte UI-/Teständerungen müssen vor einem PR noch committed und gepusht werden; formelles Review und CI stehen aus.

Nach EG- und Zugangskorrektur: 213 Django-Tests erfolgreich. Systemcheck, Migrationsprüfung, Ruff und Formatprüfung erfolgreich. Im Browser geprüft: EG-Vektorplan, Klickweg zur Wohnungsdetailseite und Weiterleitung zur wohnungsbezogenen Anfrage über die Anmeldung. Der Teststand enthält den zwischenzeitlich integrierten Wegfall der öffentlichen Barrierefreiheitsangabe und fünf neue Tests zum Besichtigungseinstieg.

Offen sind die Bestätigung der räumlichen Wohnungsnummernzuordnung, echte Fotos und reale Angaben zu Zimmern, Kosten und Ausstattung. Der erste Stand wurde vom Nutzer als 9fba447 gepusht. Die anschließenden EG- und Zugangskorrekturen liegen lokal. US-02 bleibt bis zur fachlichen Abnahme und zum Review offen.

## EG-Korrektur nach Review

Nach den ersten Einzelkorrekturen hat der Nutzer eine eigene vereinfachte EG-Skizze bereitgestellt. Nach weiterer Rückmeldung wird sie als geometrische Orientierung genutzt, nicht als wörtliche Nachzeichnung ihrer ungeraden Linien und Markierungsfarben. Wandsegmente und Auswahlflächen sind gemeinsam begradigt und ausgerichtet, Türöffnungen und Balkonanschlüsse erhalten. Der zusätzliche linke Wandstummel an der Tür neben dem Treppenbereich ist entfernt. Gemeinschaftsbereiche ergänzen die Darstellung im bisherigen Stil; im EG gibt es keine Möbel- oder Stellplatzdarstellung mehr. Die bisher angenommene Nummernzuordnung bleibt erhalten und muss bestätigt werden; Diese EG-Korrekturen betreffen nur das Erdgeschoss; die späteren OG-/DG-Anpassungen sind oben beschrieben.

Letzter EG-Detailabgleich: In Wohnung 1 liegt die Badtür in der senkrechten Trennwand, die oben an die Außenwand anschließt; die Wohnungseingangstür liegt direkt neben dieser Wand. In Wohnung 5 zeigt der kleine Abschluss am Abstellraum nach links. Die Treppe nutzt die ganze Breite des Treppenbereichs, endet aber vor der seitlichen Wohnungstür; die zusätzliche Treppenbeschriftung entfällt. Der nördliche Zugang ist als „Eingang“ markiert. Die Innenwand in Wohnung 3 reicht bis zur unteren Außenwand. Eine Trennwand gliedert den Rollstuhl-Eingangsbereich neben dem Fahrradraum ab. Drei nördliche Eingänge sind nach den Türbögen der Vorlage dargestellt; der Rollstuhl-Eingangsbereich hat einen offenen Durchgang zum Flur. Zusätzliche unbestätigte Türbögen zum Flur entfallen.

## Warum mehrere neue Dateien?

Ein Template ist die Vorlage einer Webseite. Dateien mit führendem Unterstrich sind kleine Teile davon: Die Gebäudeseite bindet die Fassade ein, die Etagenansicht den Plan, die Detailseite die Galerie. Diese Bausteine laufen zusammen in derselben Django-Anwendung. Sie sind keine zusätzlichen Apps oder Programme.

building_plans.py liefert Nummern, Etagen, Flächen und grafische Auswahlkoordinaten. Die sichtbaren Wände und Räume stehen dagegen in _floor_plan_architecture.html. Beide müssen zusammen geändert werden, damit anklickbare Flächen und Zeichnung übereinstimmen. Die beiden Verwaltungsbefehle betreffen ausschließlich Entwicklungs-/Beispieldaten: seed_standard_data legt sie an, sync_building_inventory gleicht einen vorhandenen alten Wohnungssatz ab. Die Migration ergänzt die Fototabelle; die Testdatei prüft Verhalten und Zugriffsschutz. Die Referenz-PNGs dienen nur dem Vergleich.

## Dateien für den Commit

Alle folgenden 36 Dateien gehören zur gemeinsamen Umsetzung einschließlich der Korrektur auf feat/16-building-apartment-view:

| Datei | Zweck |
|---|---|
| README.md | Einstieg und Verweis auf diese Dokumentation. |
| config/settings.py | Größen- und Mengenlimit für Wohnungsfotos. |
| static/css/app.css | Fassaden-/Plan-Darstellung, Hover, Beschriftungen, Galerie und mobiles Layout. |
| static/js/apartment-gallery.js | Gezielte UIkit-Aufräumroutine bei schnellem Schließen der Fotogalerie. |
| templates/base.html | Header-Link zur Gebäudeansicht und Stylesheet-Version. |
| templates/wohnungsverwaltung/building_view.html | Eigene Gebäudeseite und Stockwerksauswahl. |
| templates/wohnungsverwaltung/_building_facade.html | Anklickbare SVG-Fassade. |
| templates/wohnungsverwaltung/_attic_floor_architecture.html | DG-Zeichnung mit Raumgrenzen, Treppe, Aufzug und zweiflügeligen Balkontüren. |
| templates/wohnungsverwaltung/_regular_floor_architecture.html | Gemeinsame bereinigte Zeichnung für alle drei Obergeschosse mit Balkonen und zweiläufiger Treppe. |
| templates/wohnungsverwaltung/floor_view.html | Eigene Etagenansicht mit Plan und Wohnungsliste. |
| templates/wohnungsverwaltung/_floor_plan.html | SVG-Rahmen, Wohnungsflächen, Links und Beschriftungen. |
| templates/wohnungsverwaltung/_floor_plan_architecture.html | Vektorzeichnung für EG, OG und DG: Wände, Flur, Aufzug, Treppen, Türen, Fenster, Möbel und Balkone. |
| templates/wohnungsverwaltung/apartment_search.html | Einstieg in die Gebäudeansicht aus der Suche. |
| templates/wohnungsverwaltung/apartment_detail_placeholder.html | Tatsächliche Detailseite, gespeicherte Angaben, Galerie, Kosten und Besichtigungslink; alter Dateiname zur Kompatibilität. |
| templates/wohnungsverwaltung/_apartment_gallery.html | Wiederverwendbare Fotogalerie und Platzhalter. |
| templates/wohnungsverwaltung/apartment_photos.html | Mitarbeiterseite zum Hochladen und Entfernen von Fotos. |
| templates/wohnungsverwaltung/wohnung_form.html | Link von der Wohnungspflege zur Fotopflege. |
| templates/wohnungsverwaltung/pre_application_form.html | Besichtigungswortlaut und Erklärung beim wohnungsbezogenen Einstieg. |
| templates/wohnungsverwaltung/viewing_request_unavailable.html | Verständliche Erklärung bei fehlendem Bewerberzugang oder Personenprofil. |
| wohnungsverwaltung/models.py | Neues ApartmentPhoto-Modell samt Dateipfad. |
| wohnungsverwaltung/forms.py | Foto-Validierung und sichere Bildaufbereitung. |
| wohnungsverwaltung/views.py | Gebäude-/Etagenansichten, Detaildaten, Fotoverwaltung/-auslieferung und Besichtigungs-Erfolgsnachricht. |
| wohnungsverwaltung/public_urls.py | Öffentliche Gebäude-, Etagen- und Foto-Routen. |
| wohnungsverwaltung/verwaltung_urls.py | Mitarbeiter-Routen für Fotoverwaltung und Löschen. |
| wohnungsverwaltung/building_plans.py | Bestätigte Wohnungsliste, vorläufige Auswahlflächen, Plan-Koordinaten und Etagenbezeichnungen. |
| wohnungsverwaltung/management/commands/seed_standard_data.py | Neue lokale Beispieldaten mit richtiger Wohnungsverteilung. |
| wohnungsverwaltung/management/commands/sync_building_inventory.py | Expliziter, geschützter Abgleich alter Entwicklungsdaten bei erhaltenen IDs. |
| wohnungsverwaltung/migrations/0020_apartment_photos.py | Additive Datenbank-Migration für Fotos. |
| wohnungsverwaltung/test_building_view.py | Tests für Navigation, Detaildaten, Fotoupload/-schutz und Inventarabgleich. |
| wohnungsverwaltung/tests.py | Aktualisierte Detail-Erwartung und Test für Besichtigungsanfrage ohne Main-Freischaltung. |
| docs/prototypes/16-building-apartment-view.md | Umsetzung, Einrichtung, Grenzen und diese Commitübersicht. |
| docs/demo-photos/README.md | Kennzeichnung und Anleitung für die vier KI-generierten Beispieldateien. |
| docs/demo-photos/01-wohnbereich.jpg | Fiktiver Wohnbereich für Tests und Vorführungen. |
| docs/demo-photos/02-kueche.jpg | Fiktive Küche für Tests und Vorführungen. |
| docs/demo-photos/03-schlafzimmer.jpg | Fiktives Schlafzimmer für Tests und Vorführungen. |
| docs/demo-photos/04-bad.jpg | Fiktives Bad als viertes Galeriebild für Tests und Vorführungen. |

Nicht in diesen Feature-Commit gehören die bereits zuvor vorhandenen unversionierten Dateien .gitattributes, .idea/, docs/prototypes/filter-design-teal.svg und docs/prototypes/filter-design-waldgruen.svg. Sie bleiben unangetastet. Ebenso keine .env-Dateien, Docker-Datenbankdaten, Uploads oder Screenshots übernehmen.

Vorgeschlagene Commit-Nachricht:

```text
feat: add building explorer and viewing request entry
```

Die 36 Dateien bilden einen zusammengehörenden Funktionsstand; Schema-Migration, Views und Templates sollten gemeinsam übernommen werden. Auf einer anderen Entwicklungsumgebung ist python manage.py migrate erforderlich. Der lokale Inventarabgleich wird bei Bedarf ausdrücklich ausgeführt, nicht automatisch beim Start.
