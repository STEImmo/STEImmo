# Gebäude- und Wohnungsansicht (US-02, #16)

Der Prototyp läuft in der bestehenden Django-Anwendung über Docker. Einstieg: http://localhost:8000/wohnungen/gebaeude/ oder „Gebäude erkunden“ im Header.

## Seiten und Grundrisse

1. Gebäudeansicht mit vereinfachter Westfassade und auswählbaren Stockwerken.
2. Eigene Etagenansicht mit einem vereinfachten SVG-Vektorgrundriss, freien anklickbaren und nicht verfügbaren ausgegrauten Wohnungen. Die Wohnungsliste ergänzt die grafische Auswahl.
3. Wohnungsdetails mit gespeicherten Werten, Fotogalerie und „Zur Besichtigung anmelden“.

Die Vektorgrafiken orientieren sich an den gelieferten EG-, OG- und DG-Zeichnungen. Flurachse, Aufzug, Treppenhaus, versetzte Konturen, Raumtrennwände und Balkonpositionen sind vereinfacht nachgebaut. OG und DG werden gemeinsam mit den Auswahlflächen gedreht; die Beschriftungen bleiben aufrecht. Die PNGs unter static/plans werden ausschließlich über „Originalplan öffnen“ als Vergleichsvorlagen angeboten, nicht als Hintergrund der dargestellten Grundrisse.

Die Darstellung ist nicht maßstabsgetreu. Die Wohnungsnummern sind den Flächen vorläufig zugeordnet und müssen fachlich bestätigt werden. Die drei Obergeschosse verwenden denselben Grundrisstyp. UIkit 3.25.24 bleibt die Komponentenbasis; es gibt keine zusätzliche Bibliothek oder eigenständige HTML-Vorschau.

## Wohnungsdaten

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

Der Button auf der Detailseite führt zur bestehenden wohnungsbezogenen Voranfrage. Nach der Anmeldung ist die Wohnung bereits ausgewählt. Formular und Erfolgsnachricht sprechen von einer Besichtigungsanfrage. Ein Besichtigungstermin wird separat bestätigt; die Anfrage bucht keinen Termin.

Intern bleibt dies eine Pre-Bewerbung im vorhandenen Bewerbung-Modell. Es wird kein zweiter Bewerbungsablauf eingeführt. Die Hauptbewerbung bleibt gesperrt, bis Mitarbeiter sie nach Besichtigung und positiver Eignungsentscheidung freigeben. Der neue Test prüft Wohnungszuordnung, erfolgreiche Anfrage und weiterhin gesperrten Hauptbewerbungszugang.

## Wohnungsfotos

Berechtigte Mitarbeiter können unter Verwaltung → Wohnung bearbeiten → Wohnungsfotos verwalten Bilder hinzufügen und entfernen. Migration 0020_apartment_photos ergänzt eine eigene Tabelle. Übergabe- und Bewerbungsdokumente werden nicht als öffentliche Wohnungsbilder verwendet.

- JPEG, PNG und WebP; maximal 8 MiB und 25 Megapixel je Bild, höchstens zwölf Fotos je Wohnung.
- Prüfung des Bildinhalts, Neucodierung als JPEG, maximal 2400 Pixel Kantenlänge, entfernte Metadaten.
- Erstes Foto als Titelbild; UIkit Lightbox für die Galerie.
- Öffentlich ausgelieferte Fotos nur für verfügbare Wohnungen; Mitarbeiter können auch andere Wohnungsfotos verwalten.
- Speicherung in MEDIA_ROOT außerhalb der Versionskontrolle; keine Freigabe des gesamten Medienverzeichnisses.
- Ohne hochgeladene Fotos bleiben neutrale Platzhalter sichtbar.

## Prüfung und offene Punkte

210 Django-Tests erfolgreich. Systemcheck, Migrationsprüfung, Ruff und Formatprüfung erfolgreich. Im Browser geprüft: Vektorpläne, Klickweg zur Wohnungsdetailseite und Weiterleitung zur wohnungsbezogenen Anfrage über die Anmeldung.

Offen sind die Bestätigung der räumlichen Wohnungsnummernzuordnung, echte Fotos und reale Angaben zu Zimmern, Kosten und Ausstattung. Es wurde nicht gepusht und kein PR erstellt. US-02 bleibt bis zur fachlichen Abnahme und zum Review offen.

## Dateien für den Commit

Alle folgenden 30 Dateien gehören zur gemeinsamen Umsetzung auf feat/16-building-apartment-view:

| Datei | Zweck |
|---|---|
| README.md | Einstieg und Verweis auf diese Dokumentation. |
| config/settings.py | Größen- und Mengenlimit für Wohnungsfotos. |
| static/css/app.css | Fassaden-/Plan-Darstellung, Hover, Beschriftungen, Galerie und mobiles Layout. |
| static/plans/ground-floor-reference.png | EG-Vorlage zum manuellen Vergleich. |
| static/plans/upper-floor-reference.png | OG-Vorlage zum manuellen Vergleich. |
| static/plans/attic-reference.png | DG-Vorlage zum manuellen Vergleich. |
| templates/base.html | Header-Link zur Gebäudeansicht und Stylesheet-Version. |
| templates/wohnungsverwaltung/building_view.html | Eigene Gebäudeseite und Stockwerksauswahl. |
| templates/wohnungsverwaltung/_building_facade.html | Anklickbare SVG-Fassade. |
| templates/wohnungsverwaltung/floor_view.html | Eigene Etagenansicht mit Plan und Wohnungsliste. |
| templates/wohnungsverwaltung/_floor_plan.html | SVG-Rahmen, Wohnungsflächen, Links und Beschriftungen. |
| templates/wohnungsverwaltung/_floor_plan_architecture.html | Vektorzeichnung für EG, OG und DG: Wände, Flur, Aufzug, Treppen, Türen, Fenster, Möbel und Balkone. |
| templates/wohnungsverwaltung/apartment_search.html | Einstieg in die Gebäudeansicht aus der Suche. |
| templates/wohnungsverwaltung/apartment_detail_placeholder.html | Tatsächliche Detailseite, gespeicherte Angaben, Galerie, Kosten und Besichtigungslink; alter Dateiname zur Kompatibilität. |
| templates/wohnungsverwaltung/_apartment_gallery.html | Wiederverwendbare Fotogalerie und Platzhalter. |
| templates/wohnungsverwaltung/apartment_photos.html | Mitarbeiterseite zum Hochladen und Entfernen von Fotos. |
| templates/wohnungsverwaltung/wohnung_form.html | Link von der Wohnungspflege zur Fotopflege. |
| templates/wohnungsverwaltung/pre_application_form.html | Besichtigungswortlaut und Erklärung beim wohnungsbezogenen Einstieg. |
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

Nicht in diesen Feature-Commit gehören die bereits zuvor vorhandenen unversionierten Dateien .gitattributes, .idea/, docs/prototypes/filter-design-teal.svg und docs/prototypes/filter-design-waldgruen.svg. Sie bleiben unangetastet. Ebenso keine .env-Dateien, Docker-Datenbankdaten, Uploads oder Screenshots übernehmen.

Vorgeschlagene Commit-Nachricht:

```text
feat: add building explorer and viewing request entry
```

Die 30 Dateien bilden einen zusammengehörenden Funktionsstand; Schema-Migration, Views und Templates sollten gemeinsam übernommen werden. Auf einer anderen Entwicklungsumgebung ist python manage.py migrate erforderlich. Der lokale Inventarabgleich wird bei Bedarf ausdrücklich ausgeführt, nicht automatisch beim Start.
