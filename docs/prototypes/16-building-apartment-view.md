# Gebäude- und Wohnungsansicht (US-02, #16)

## Aktueller Datenstand und Vereinfachung vom 9. Oktober 2026

Die aktuelle Excel-Wohnungsliste des Nutzers ist die maßgebliche Flächenquelle. Alle 25 gespeicherten Nummern, Etagen und Flächen stimmen damit überein, einschließlich DG 401 mit 92,94 m² und 402 mit 64,90 m². Wohnungsangaben, Fotos, Suchfilter und Verfügbarkeitszahlen kommen zur Laufzeit ausschließlich aus der Datenbank. Änderungen über die Mitarbeiterverwaltung erscheinen beim nächsten Seitenaufruf ohne Codeänderung.

Auf ausdrücklichen Nutzerwunsch bleibt das bisherige Pflichtfeldschema erhalten: Zimmerzahl, Kalt-/Warmmiete und Kaution haben weiterhin den bestehenden Standardwert 0; der Status ist frei, vermietet oder gesperrt. Es gibt keine neue Migration 0022 und keine NULL-Erweiterung. Die nur lokal angewandte 0022 wurde nach Sicherung des aktuellen Wohnungsbestands außerhalb des Repositorys geordnet auf 0021 zurückgenommen. Die ursprünglichen Migrationen wurden nicht umgeschrieben. Fehlende Zahlen wurden auf den bestehenden Standard 0 gesetzt; bereits gepflegte Werte bleiben erhalten. Die zwischenzeitliche pauschale Sperrung aller 25 Wohnungen wurde auf ausdrücklichen Nutzerwunsch für die lokale Datenbank rückgängig gemacht: Die vor der Bereinigung gesicherten Statuswerte sind wiederhergestellt (16 frei, 8 vermietet, 1 gesperrt). Dabei wurde ausschließlich das Statusfeld geändert; alle anderen Wohnungswerte und Fotoverknüpfungen blieben unverändert. Die früheren erfundenen Mieten und Zimmerzahlen wurden nicht wiederhergestellt. Die lokalen Verfügbarkeitswerte dienen weiterhin der Entwicklung und sind keine Bestätigung der tatsächlichen späteren Vermietung.

Öffentlich werden numerische Standardwerte 0 bei Zimmern und Kosten als „Noch nicht angegeben“ angezeigt. Bei Miet-/Zimmerfiltern werden diese unvollständigen Angaben ausgeschlossen, statt fälschlich als besonders günstig oder kleine Zimmerzahl zu erscheinen. Mit dem bisherigen Schema lässt sich ein echter Nullbetrag nicht von einem nicht gepflegten Standardwert unterscheiden; deshalb wird 0 in diesen öffentlichen Angaben einheitlich als fehlend behandelt. Ein frei gepflegter Status steuert Suche, Detailzugriff, Fotozugriff und den bestehenden Besichtigungseinstieg. Vermietete/gesperrte Wohnungen bleiben schraffiert, nicht auswählbar und vor öffentlichem Detail-/Fotozugriff geschützt.

Entfernt wurden die zusätzliche Testdatei, der erledigte Bereinigungsbefehl und die eigene Inventardatei. Die verbleibenden fachlichen Regressionstests stehen in test_building_view.py. Die bestätigte Excel-Einrichtungsvorlage liegt nur noch im vorhandenen seed_standard_data-Befehl und wird vom bestehenden Entwicklungsabgleich wiederverwendet; öffentliche Views importieren sie nicht. Seed und Abgleich überschreiben bereits gepflegte aktuelle Angaben nicht. Neu angelegte Entwicklungswohnungen sind gesperrt und enthalten keine erfundenen Zimmer- oder Kostenwerte. AGENTS.md ist unverändert.

**US-02:** Gebäude- und Etagenauswahl, DB-basierte Details, Galerie, Verfügbarkeitsdarstellung und der wohnungsbezogene Pre-Bewerbungseinstieg bleiben implementiert. Heizung, Ausstattung und andere Angaben werden angezeigt, sofern sie gespeichert sind, sonst einzeln als fehlend gekennzeichnet. Die öffentliche Barrierefreiheitsangabe bleibt gemäß ausdrücklicher Auftraggeberentscheidung entfernt. Die vier auf Nutzerwunsch behaltenen KI-Testbilder bleiben gekennzeichnet; echte Wohnungsfotos sind noch zu pflegen. Beschreibung und Checklisten der GitHub-Story bleiben unverändert.

**Offene reale Daten:** Zimmerzahl je Wohnungsnummer, Mietbeträge einschließlich Kostenumfang, Kaution, Ausstattung, Heizung und Energieangaben. Die Gesamtverteilung 12 Einzimmer-, 11 Zweizimmer- und 2 Drei-/Dreieinhalbzimmerwohnungen ist bekannt, erlaubt aber im Bereich 40–47 m² keine sichere Einzelzuordnung. Der tatsächliche Status muss in der Mitarbeiterverwaltung gepflegt werden. Die Technik dafür ist vorhanden; fehlende Daten werden nicht erraten. Belegte Projektbeschreibung und voraussichtlicher Einzug März 2027 bleiben erhalten. Unabhängiges Review und fachliche Abnahme stehen aus; kein Commit oder Push ausgeführt.

**Prüfung dieser Vereinfachung:** Alle 238 Django-Tests erfolgreich, darunter 42 gezielte Tests für Gebäudeansicht, Galerie, Zugriffsschutz und Einrichtung. Django-Systemcheck, Prüfung auf ausstehende Migrationen, Ruff-Codeprüfung, Ruff-Formatprüfung und Diff-Prüfung erfolgreich. Nach der lokalen Statuswiederherstellung die 42 gezielten Tests erneut erfolgreich ausgeführt. Gegen den tatsächlichen lokalen Bestand zusätzlich alle fünf Etagen sowie den Detailzugriff aller 25 Wohnungen geprüft: 16 freie Wohnungen erreichbar, 9 vermietete/gesperrte Wohnungen öffentlich nicht erreichbar. Im Browser Gebäude → Erdgeschoss → Wohnung 001 geprüft: 16 verfügbare Wohnungen insgesamt, freie Flächen auswählbar, vermietete Fläche schraffiert, Detailseite und Galerie erreichbar, unbestätigte Zahlen als fehlend gekennzeichnet. Der lokale Bestand enthält unverändert 25 Wohnungen mit bestätigten Excel-Flächen und 4 Testfotos; Migration 0022 ist nicht mehr angewandt.

**Abschließende Browserprüfung vom 9. Oktober 2026:** Detailansicht bei 320, 390, 768 und 1440 Pixeln geprüft; alle fünf Etagen bei 320 Pixeln geprüft. Die Seite läuft dabei nicht seitlich über; der Grundriss ist innerhalb seines eigenen Bereichs seitlich scrollbar. Galerie mit drei Vorschauen und Stapelhinweis, Durchblättern zum vierten Foto, normales Schließen und schnelles Schließen per Escape geprüft. Ein dabei reproduzierter Konsolenfehler in UIkit 3.25.24 (`getAnimations` auf einem fehlenden Übergangspanel) wurde durch die vorhandene Lightboxoption `sel-panel` korrigiert. `bg-close: false` verhindert, dass außerhalb des Bildpanels liegende Navigationsbuttons die Lightbox schließen; Schließen erfolgt über den Button oder Escape. Keine Bibliothek oder UIkit-Version geändert. Der bestehende Galerie-Response-Test sichert die Konfiguration ab; die Browserwiederholung auf Handy und Desktop zeigte keine neuen Konsolenfehler oder Scrollsperren.

**Integrationsstand:** Der aktuelle Remote-main wurde lesend abgerufen (b8b167e). Der US-02-Branch ist funktional geprüft, aber noch nicht mergebereit: Die probeweise Zusammenführung ohne Änderung des Arbeitsbranches meldet Konflikte in config/settings.py, templates/base.html, templates/wohnungsverwaltung/wohnung_form.html, wohnungsverwaltung/forms.py und wohnungsverwaltung/views.py. Zudem bestehen getrennte Migrationszweige für Wohnungsdetails und die inzwischen auf main vorhandenen Bewerbungs-/Dokumentänderungen; sie müssen bei der Integration geordnet zusammengeführt werden. Die bestehende UIkit-Grundlage ist kompatibel, die Kombination mit dem neuen Theme und den weiteren main-Änderungen ist noch nicht validiert. Vor Ready for Review den aktuellen main integrieren und alle Checks erneut ausführen. GitHub-Issue und AGENTS.md wurden bei dieser Prüfung nicht verändert.

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

Die vom Nutzer bestätigte Excel-Liste ist als reine Einrichtungsvorlage im vorhandenen seed_standard_data-Befehl hinterlegt; angezeigte Wohnungswerte stammen aus der Datenbank:

- EG: 1–5, fünf Wohnungen
- 1. OG: 101–106, sechs Wohnungen
- 2. OG: 201–206, sechs Wohnungen
- 3. OG: 301–306, sechs Wohnungen
- DG: 401–402, zwei Wohnungen

Nummern, Etagen und Flächen wurden in der lokalen Entwicklungsdatenbank abgeglichen. IDs und Fremdschlüssel bleiben erhalten. Mieten, Zimmerzahlen und Status stammen weiterhin aus den vorhandenen Beispieldaten; die neue Wohnungsliste bestätigt diese Werte nicht.

Wohnfläche, Zimmer, Mieten, Kaution, Status und Fotos sind im System hinterlegt beziehungsweise pflegbar. Beschreibung, Ausstattung, Heizungstyp, Energieangaben und geplanter Einzug werden seit Migration `0021_apartment_public_details` als optionale Wohnungsfelder in der Verwaltung gepflegt. Fehlende Angaben erscheinen auf der Detailseite einzeln als „Noch nicht angegeben“. Mehrzeilige Texte werden als escaped Text mit Zeilenumbrüchen dargestellt; eingegebenes HTML wird nicht ausgeführt. Für den geplanten Einzug ist eine ungefähre Textangabe möglich, ohne ein unbelegtes Tagesdatum zu erfinden. Ein Energieausweis-Upload ist nicht Bestandteil dieser Erweiterung. Lagebeschreibung und Kostenaufschlüsselung werden weiterhin nicht eigens gepflegt; der Hinweis zu fehlenden Kostendetails bleibt erhalten. Die öffentliche Barrierefreiheitsangabe entfällt gemäß Auftraggeberentscheidung.

Die lokale Entwicklung und `seed_standard_data` ergänzen ausschließlich leere Beschreibungen und Einzugsangaben mit belegten Projektinformationen: Umbau eines Bestandsgebäudes in Würzburg, Wohnanlage mit 25 Einheiten, Schwerpunkt Studierende, geplanter Erstbezug März 2027. Individuell gepflegte Detailtexte bleiben beim erneuten Seed erhalten. Ausstattung, Heizungsart und Energiekennwerte werden nicht aus Planzeichnungen oder Möbeln abgeleitet und bleiben zunächst leer. Quellen: [Projektpitch](https://drive.google.com/file/d/1Z6vXQ0n6QF-1dPcyZrBSp2pUK5_UGXj5/view) und [Präsentation vom 23.09.2026](https://docs.google.com/presentation/d/13qISXTeQAF99jrCga_LmigeaW8Wyg3ra_aGRE3CpFrw/edit). Auf bestehenden anderen Umgebungen zuerst migrieren und die Angaben über „Wohnung bearbeiten → Öffentliche Detailangaben“ ergänzen; `seed_standard_data` ist wegen weiterer Beispielwerte kein Aktualisierungsbefehl für reale Daten.

US-02: Die vom Agenten angehängten Fortschrittsnotizen wurden auf Nutzerauftrag am 09.10.2026 aus der Issue-Beschreibung entfernt. Story, Kriterien, Einordnung und vorhandene Häkchen wurden ansonsten unverändert gelassen. Weitere Fortschrittsberichte werden als Kommentartext zum manuellen Einfügen bereitgestellt.

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

Review-Korrekturen vom 09.10.2026:

- Die Auswahlflächen sind über Etage und öffentliche Wohnungsnummer fest zugeordnet. Fehlende Wohnungen verschieben die übrigen Flächen nicht. Unbekannte oder doppelte Nummern werden nicht auf fremde Flächen gelegt; die Etagenansicht verweist dann auf die vollständige Wohnungsliste. Außerhalb der fünf unterstützten Etagen werden keine Fassaden-/Navigationslinks erzeugt; direkte Etagenaufrufe liefern 404.
- Bildbeschreibungen werden für beide Verarbeitungsschritte escaped: für das HTML-Attribut und für die HTML-Ausgabe der UIkit-Lightbox. Gespeicherte Beschreibungen und Alternativtexte bleiben unverändert. HTML-Zeichen werden auch in der Lightbox als Text dargestellt; es gibt keine HTML-Freigabe für Bildbeschreibungen.
- Fotolöschen sperrt den betroffenen Datensatz und führt Datenbank- sowie Dateilöschung innerhalb einer Datenbanktransaktion aus. Bei einem Dateispeicherfehler wird die Datensatzlöschung zurückgerollt. Bei einem Datenbankfehler vor der Dateilöschung bleibt auch die Datei erhalten. Die Verwaltung zeigt einen verständlichen Fehler und erlaubt einen erneuten Versuch. Datenbank und Dateisystem bilden weiterhin keine gemeinsame atomare Transaktion: Ein Verbindungs-/Commitfehler nach erfolgreicher Dateilöschung kann eine Speicherprüfung und Wiederherstellung aus dem Backup erfordern.
- Regressionstests prüfen diese Fehler sowie zusätzliche/doppelte Nummern, nicht unterstützte Etagen, Sonderzeichen in Beschreibungen und Berechtigungen/CSRF beim Löschen. Die bereits beanstandete zusätzliche Leerzeile am Ende des Architektur-Templates ist entfernt. Keine neue Migration oder Abhängigkeit ist erforderlich.

Abschließende Prüfung dieser Korrekturen: 34 gezielte Tests und anschließend alle 232 Django-Tests erfolgreich. Systemcheck, Migrationsprüfung, Ruff einschließlich Formatprüfung sowie Diff-Prüfung des Arbeitsstands und des gesamten Stands gegen `main` erfolgreich. Im Browser die tatsächlich gerenderte UIkit-Lightbox auf einer isolierten Prüfseite mit HTML-Zeichen, Ampersand und Anführungszeichen kontrolliert: reine Textknoten, korrekt geladene Bilder und aufgehobene Scrollsperre nach dem Schließen. Der tatsächliche Etagenplan wurde nach den Korrekturen neu geladen und geprüft; die unveränderten Positionen bleiben korrekt zugeordnet. Testdateien und Screenshots liegen außerhalb des Repositorys; gespeicherte Wohnungs- und Fotodaten wurden für die Browserprüfung nicht verändert. Die GitHub-Story bleibt unverändert.

Detailangaben am 09.10.2026: 224 Django-Tests erfolgreich; Systemcheck, Migrationsprüfung und Ruff-Prüfungen erfolgreich. Migration 0021 lokal angewendet. Im Browser öffentliche Angaben auf Desktop und Mobilgerät ohne Seitenüberlauf geprüft sowie Mitarbeiteranmeldung mit Einmalcode, Detailfelder und erfolgreiches Speichern über die Verwaltung geprüft. Ausstattung, Heizung und Energie bleiben bis zu belegten Angaben offen. Kein Commit, Push oder PR durch den Agenten.

Nach der Galerie-Korrektur: 24 relevante Django-Tests, Systemcheck, Migrationsprüfung, Ruff und Formatprüfung erfolgreich. Im Browser geprüft: drei sichtbare Fotos auf Desktop und Mobilgeräten, Stapelhinweis auf dem dritten Foto, geladene vergrößerte Bilder und Zugriff auf das vierte Foto. Nach normalem und sofortigem Schließen ist die Lightbox entfernt und die Seite wieder scrollbar. Die GitHub-User-Story wurde in dieser Runde nicht verändert.

Vor der letzten Galerie-Korrektur: 219 Django-Tests erfolgreich, einschließlich Galerie mit mehr als drei Fotos. Vier mit Imagegen erzeugte Demo-Fotos (Wohnbereich, Küche, Schlafzimmer, Bad) sind in der lokalen Fotopflege von Wohnung 001 hinterlegt und als „Demo – KI-Beispiel“ beschriftet. Vergrößern und Weiterblättern in der UIkit-Lightbox wurden nach der Galerie-Korrektur im Browser erfolgreich geprüft. Die Arbeitskopien im Medienbereich gehören nicht in Git; die ausdrücklich freigegebenen Beispieldateien unter `docs/demo-photos/` dürfen mitcommitted werden. Sie zeigen nicht die tatsächliche Immobilie. Barrierefreiheit entfällt nach Auftraggeberentscheidung; Heizung/Ausstattung dürfen laut Nutzer vorerst Platzhalter bleiben. Letzte UI-/Teständerungen müssen vor einem PR noch committed und gepusht werden; formelles Review und CI stehen aus.

Nach EG- und Zugangskorrektur: 213 Django-Tests erfolgreich. Systemcheck, Migrationsprüfung, Ruff und Formatprüfung erfolgreich. Im Browser geprüft: EG-Vektorplan, Klickweg zur Wohnungsdetailseite und Weiterleitung zur wohnungsbezogenen Anfrage über die Anmeldung. Der Teststand enthält den zwischenzeitlich integrierten Wegfall der öffentlichen Barrierefreiheitsangabe und fünf neue Tests zum Besichtigungseinstieg.

Offen sind die Bestätigung der räumlichen Wohnungsnummernzuordnung, echte Fotos und reale Angaben zu Zimmern, Kosten und Ausstattung. Der erste Stand wurde vom Nutzer als 9fba447 gepusht. Die anschließenden EG- und Zugangskorrekturen liegen lokal. US-02 bleibt bis zur fachlichen Abnahme und zum Review offen.

## EG-Korrektur nach Review

Nach den ersten Einzelkorrekturen hat der Nutzer eine eigene vereinfachte EG-Skizze bereitgestellt. Nach weiterer Rückmeldung wird sie als geometrische Orientierung genutzt, nicht als wörtliche Nachzeichnung ihrer ungeraden Linien und Markierungsfarben. Wandsegmente und Auswahlflächen sind gemeinsam begradigt und ausgerichtet, Türöffnungen und Balkonanschlüsse erhalten. Der zusätzliche linke Wandstummel an der Tür neben dem Treppenbereich ist entfernt. Gemeinschaftsbereiche ergänzen die Darstellung im bisherigen Stil; im EG gibt es keine Möbel- oder Stellplatzdarstellung mehr. Die bisher angenommene Nummernzuordnung bleibt erhalten und muss bestätigt werden; Diese EG-Korrekturen betreffen nur das Erdgeschoss; die späteren OG-/DG-Anpassungen sind oben beschrieben.

Letzter EG-Detailabgleich: In Wohnung 1 liegt die Badtür in der senkrechten Trennwand, die oben an die Außenwand anschließt; die Wohnungseingangstür liegt direkt neben dieser Wand. In Wohnung 5 zeigt der kleine Abschluss am Abstellraum nach links. Die Treppe nutzt die ganze Breite des Treppenbereichs, endet aber vor der seitlichen Wohnungstür; die zusätzliche Treppenbeschriftung entfällt. Der nördliche Zugang ist als „Eingang“ markiert. Die Innenwand in Wohnung 3 reicht bis zur unteren Außenwand. Eine Trennwand gliedert den Rollstuhl-Eingangsbereich neben dem Fahrradraum ab. Drei nördliche Eingänge sind nach den Türbögen der Vorlage dargestellt; der Rollstuhl-Eingangsbereich hat einen offenen Durchgang zum Flur. Zusätzliche unbestätigte Türbögen zum Flur entfallen.

## Warum mehrere neue Dateien?

Ein Template ist die Vorlage einer Webseite. Dateien mit führendem Unterstrich sind kleine Teile davon: Die Gebäudeseite bindet die Fassade ein, die Etagenansicht den Plan, die Detailseite die Galerie. Diese Bausteine laufen zusammen in derselben Django-Anwendung. Sie sind keine zusätzlichen Apps oder Programme.

building_plans.py liefert die grafischen Auswahlkoordinaten und Etagenbezeichnungen; Nummern, Etagen und Flächen der angezeigten Wohnungen kommen aus der Datenbank. Die sichtbaren Wände und Räume stehen dagegen in _floor_plan_architecture.html. Beide müssen zusammen geändert werden, damit anklickbare Flächen und Zeichnung übereinstimmen. Die beiden Verwaltungsbefehle betreffen ausschließlich Entwicklungs-/Beispieldaten: seed_standard_data legt sie an, sync_building_inventory gleicht einen vorhandenen alten Wohnungssatz ab. Die Migration ergänzt die Fototabelle; die Testdatei prüft Verhalten und Zugriffsschutz. Die Referenz-PNGs dienen nur dem Vergleich.

## Dateien für den Commit

Alle folgenden 38 Dateien gehören zur gemeinsamen Umsetzung einschließlich der Korrektur auf feat/16-building-apartment-view:

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
| wohnungsverwaltung/building_plans.py | Auswahlflächen, Plan-Koordinaten und Etagenbezeichnungen; keine fachlichen Wohnungswerte. |
| wohnungsverwaltung/management/commands/seed_standard_data.py | Neue lokale Beispieldaten mit richtiger Wohnungsverteilung. |
| wohnungsverwaltung/management/commands/sync_building_inventory.py | Expliziter, geschützter Abgleich alter Entwicklungsdaten bei erhaltenen IDs. |
| wohnungsverwaltung/migrations/0020_apartment_photos.py | Additive Datenbank-Migration für Fotos. |
| wohnungsverwaltung/migrations/0021_apartment_public_details.py | Additive Migration für optionale öffentliche Detailangaben. |
| wohnungsverwaltung/test_building_view.py | Tests für Navigation, Detaildaten, Fotoupload/-schutz und Inventarabgleich. |
| wohnungsverwaltung/tests.py | Aktualisierte Detail-Erwartung und Test für Besichtigungsanfrage ohne Main-Freischaltung. |
| wohnungsverwaltung/test_management.py | Speichern und Leerlassen der optionalen Detailangaben über die Mitarbeiterverwaltung. |
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

Die 38 Dateien bilden einen zusammengehörenden Funktionsstand; Schema-Migration, Views und Templates sollten gemeinsam übernommen werden. Auf einer anderen Entwicklungsumgebung ist python manage.py migrate erforderlich. Der lokale Inventarabgleich wird bei Bedarf ausdrücklich ausgeführt, nicht automatisch beim Start.
