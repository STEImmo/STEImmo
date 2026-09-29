# ADR-0008: UIkit-Theme und Design-Token-Ablage

- Status: Proposed
- Datum: 2026-09-29
- Geltungsbereich: STEImmo-Django-Monolith
- Issue: #47
- Folgestories: #45 und #46

## Kontext

Das Projekt verwendet serverseitige Django-Templates und lokal versionierte UIkit-Assets. `templates/base.html` bindet `static/vendor/uikit/uikit.min.css`, die UIkit-Skripte und `static/css/app.css` global ein. `app.css` enthält derzeit nur eine Grundregel für die Mindesthöhe des Dokuments.

Es gibt bereits eine öffentliche Bewerbungsvorschau (`templates/wohnungsverwaltung/pre_application_preview.html`) und eine staff-geschützte Verwaltungsliste (`templates/wohnungsverwaltung/wohnung_list.html`). Beide erweitern `base.html`. In der Vorlage der Wohnungsliste wird eine UIkit-Tabelle derzeit in einem horizontal scrollbar gehaltenen Container dargestellt. Die lokale UIkit-CSS-Datei unterstützt `uk-table-responsive`; diese Regel blendet auf kleineren Ansichten die Tabellenüberschrift aus und stapelt Zellen. Die bestehende Liste liefert dabei noch keine sichtbaren Feldnamen je Zelle.

Das Designfundament soll ohne zweite UI-Bibliothek, separate Frontend-Anwendung oder neue Build-Toolchain auskommen. Es darf keine fachlichen Abläufe, Felder, Berechtigungen oder Daten verändern. Die vorhandene UIkit-Distribution ist bereits kompiliertes CSS; die enthaltenen CSS-Custom-Properties sind keine frei verwendbaren Design-Tokens für Farben und Typografie. Eigene STEImmo-Variablen ändern UIkit-Komponenten deshalb nicht automatisch.

## Entscheidungsvorschlag

1. **Design-Tokens und Theme-CSS** liegen zunächst in `static/css/app.css`. Dort werden wenige semantische CSS-Custom-Properties für Text, Flächen, Ränder, Aktionen, Status, Fokus, Schriftgrößen, Zeilenabstände und Abstände definiert. Die konkreten Markenfarben und endgültigen Werte werden in #45 festgelegt.
2. **UIkit bleibt die einzige Komponentenbasis.** UIkit-Klassen strukturieren die Templates. `app.css` definiert semantische STEImmo-Tokens und bildet sie mit wenigen, gezielten Selektoren auf die tatsächlich verwendeten UIkit-Zustände ab (zum Beispiel Primärbutton, Links, Formularfelder, Statushinweise und Fokus). Die Tokens allein ändern das gebündelte UIkit-CSS nicht. Die versionierten UIkit-Dateien unter `static/vendor/uikit/` werden nicht direkt verändert. Falls die nötigen Overrides breit oder wartungsintensiv werden, wird die Theme-Strategie neu bewertet.
3. **Vorlagenzuständigkeit:** `templates/base.html` bleibt für den globalen Seitenrahmen, die Navigation und globale Django-Meldungen zuständig. Wirklich app-übergreifende Bausteine können unter `templates/partials/` liegen. App-spezifische Bausteine verbleiben bei der jeweiligen App und folgen der vorhandenen Unterstrich-Konvention, zum Beispiel `templates/wohnungsverwaltung/_form_field.html`.
4. **Interaktion:** UIkit-JavaScript reicht für UIkit-Komponenten aus. Vanilla JavaScript kommt nur für einen konkreten Bedarf hinzu; eine neue Abhängigkeit oder Frontend-Buildchain ist für das Fundament nicht erforderlich.
5. **Semantik und Barrierefreiheit:** Zustände werden nicht allein durch Farbe kenntlich gemacht. Formularbeschriftungen bleiben sichtbar, Feldfehler stehen am betroffenen Feld, Statusmeldungen enthalten verständlichen Text und Tastaturfokus bleibt sichtbar. Farben und Fokus werden gegen WCAG 2.2 AA geprüft.

### Vorläufige Befunde aus der Codeprüfung

- `base.html` platziert die Navigationslinks inline in der Navbar; ein eigener Menü-Schalter für schmale Ansichten ist noch nicht vorhanden. Ein responsiver Prototyp muss die Navigation daher auf Mobilbreite sichtbar zugänglich machen.
- Die Formularpartials zeigen Labels und feldnahe Fehlertexte. Der gemeinsame Partial `_form_field.html` verknüpft Fehlertexte derzeit jedoch nicht programmatisch mit dem zugehörigen Eingabefeld.
- Die Wohnungsliste verwendet aktuell einen horizontal scrollbar gehaltenen Tabellencontainer. UIkits `uk-table-responsive` stapelt Zellen, blendet aber die Kopfzeile aus; pro Zelle sichtbare Bezeichnungen sind deshalb erforderlich.
- Eine eigene Verwaltungsübersichtsroute existiert noch nicht. Der Dashboard-Entwurf bleibt eine statische Navigationsskizze zu vorhandenen Bereichen.
- Die lokale Browserprüfung konnte nicht ausgeführt werden, weil die Browser-Sitzung `localhost:8000` nicht erreichen konnte. Mobile Darstellung, tatsächlicher Tastaturfokus und Formularzustände sind damit noch nicht visuell bestätigt.
### Skizze des repräsentativen Prototyps

Die folgenden Skizzen verwenden vorhandene Seiten und Routen; sie führen keine fachliche Funktion ein.

#### Öffentlich: Bewerbungsvorschau

```text
┌ STEImmo ─────────────────────── Menü ┐
│ Bewerbungsvorschau                   │
│ Bewerbungsformular                   │
│ [Hinweis: Vorschau speichert nichts] │
│                                      │
│ Persönliche Angaben                  │
│ Vorname*       [________________]    │
│ E-Mail*        [________________]    │
│ Wohnungswunsch [________________]    │
│                                      │
│ [Vorschau: Eingaben werden geprüft]  │
│                        [Abgabe aus]  │
└──────────────────────────────────────┘
```

Bei einem ungültigen Feld steht die Fehlermeldung direkt unter der sichtbaren Beschriftung und wird programmatisch dem Eingabefeld zugeordnet. Der Vorschauhinweis bleibt als Text verständlich. Auf schmalen Ansichten stehen Formularfelder untereinander; die Navigation kann mit UIkit-Komponenten einklappen. Die vorhandene deaktivierte Abgabe bleibt fachlich unverändert.

#### Intern: Verwaltungsübersicht

Im Repository gibt es noch keine eigene Dashboard-Übersichtsseite. Die Skizze verwendet deshalb nur bestehende Bereiche und Links; sie schlägt weder neue Kennzahlen noch neue Abläufe vor.

```text
┌ STEImmo ─────────────────────── Menü ┐
│ Verwaltung / Übersicht               │
│ Wohnungsverwaltung                   │
│                                      │
│ ┌ Wohnungen verwalten ─────────────┐ │
│ │ 25 Einheiten                     │ │
│ │ Stammdaten ansehen und pflegen → │ │
│ └──────────────────────────────────┘ │
│ ┌ Übergabeprotokolle ──────────────┐ │
│ │ Protokolle ansehen und bearbeiten→│ │
│ └──────────────────────────────────┘ │
└──────────────────────────────────────┘
```

Die Karten sind lediglich ein Navigationsmuster zu bereits vorhandenen Seiten. Die 25 Einheiten entsprechen dem bestehenden MVP-Umfang; es werden keine dynamischen Kennzahlen oder fachlichen Dashboard-Funktionen vorweggenommen.

#### Interne Liste: Wohnungsliste

```text
┌ STEImmo ─────────────────────── Menü ┐
│ Verwaltung / Wohnungen               │
│ Wohnungen                [+ Anlegen] │
│ Wohnungsstammdaten und Schlüssel     │
│                                      │
│ Gebäude  Wohnung  Etage  Größe Status│
│ 1        01       EG     62 m² Frei  │
│ 1        02       1. OG  48 m² Belegt│
│                                      │
│ Leere Liste: nächste Aktion erklären│
└──────────────────────────────────────┘
```

Auf breiten Ansichten bleibt die dichte Tabellenansicht geeignet. Auf schmalen Ansichten muss jede gestapelte Zelle ihre Feldbezeichnung sichtbar behalten; UIkits `uk-table-responsive` darf nicht ohne diese Ergänzung eingesetzt werden, weil es die Tabellenkopfzeile ausblendet. Der Status enthält zusätzlich zum Farbton einen lesbaren Statusnamen. Die leere Liste erklärt, wie eine Wohnung angelegt werden kann.

#### Gemeinsame Zustände

- Primäre, sekundäre und destruktive Aktionen unterscheiden sich in Rolle und Beschriftung.
- Erfolg, Warnung, Fehler und Information zeigen jeweils Text plus UIkit-Statusgestaltung.
- Fokus ist für Links, Buttons und Felder bei Tastaturbedienung klar erkennbar und wird nicht abgeschnitten oder überdeckt.
- Formulare zeigen sichtbare Labels, optionale Hilfetexte, Pflichtfeldhinweise und feldnahe Fehlermeldungen.

### Manuelle Prüfpunkte für den Spike

- Öffentliche Vorschau und interne Wohnungsliste bei breitem Desktop- und schmalem Mobil-Viewport ansehen.
- Beide Seiten vollständig mit der Tastatur bedienen und den Fokuspfad prüfen.
- Die Form mit leerem beziehungsweise ungültigem Feldzustand betrachten; prüfen, ob der Fehler direkt zugeordnet und verständlich ist.
- Textkontrast mindestens 4,5:1 für normalen Text und 3:1 für großen Text prüfen; sicherstellen, dass der Tastaturfokus sichtbar bleibt.
- Bei schmalem Viewport prüfen, ob Tabellenwerte verständliche Feldnamen behalten und Aktionen ohne dekoratives horizontales Scrollen erreichbar sind.

## Betrachtete Alternativen

- **UIkit-Dateien direkt ändern:** verworfen, weil Vendor-Dateien dann Projektanpassungen und Bibliotheksversion vermischen und Updates erschweren.
- **UIkit aus Sass-Quellen mit Theme-Variablen und Hooks neu kompilieren:** UIkits dokumentierter Weg für tiefe Theme-Anpassungen; für den aktuellen Spike zunächst zurückgestellt, weil das Repository nur die fertige Distribution enthält und eine zusätzliche Quelle-/Kompilierkette gepflegt werden müsste. Diese Option wird neu bewertet, falls gezielte CSS-Overrides unübersichtlich werden.
- **CSS-Custom-Properties ohne UIkit-Overrides:** verworfen, weil die vorhandene UIkit-Distribution die STEImmo-Tokens nicht automatisch verwendet.
- **Zusätzliches UI-Framework:** verworfen, weil UIkit verbindlich ist und ein zweites Framework eine zweite Komponentenpalette sowie zusätzliche Wartung erzeugen würde.
- **Ein globales Partial für jedes Element vorab anlegen:** verworfen; Partials sollen erst für tatsächlich wiederkehrende, verständliche Muster entstehen.

## Konsequenzen

- #45 kann die konkreten semantischen Farben und Typografie-/Abstandsskalen in der vorhandenen Projekt-CSS-Datei definieren, ohne UIkit-Dateien anzupassen.
- #46 kann gemeinsame Navigations-, Formular-, Status- und Listenmuster in Django-Templates umsetzen und dieselben Tokens verwenden.
- Mobile Tabellen benötigen sichtbare Feldbezeichnungen pro gestapelter Zelle oder eine andere geprüfte Darstellung; `uk-table-responsive` allein erfüllt das nicht.
- Dieses ADR legt die technische Ablage und Zuständigkeitsgrenzen fest, nicht das endgültige Corporate Design.
- Es werden keine Datenmodelle, URLs, Berechtigungen oder fachlichen Abläufe verändert.

## Referenzen

- [UIkit: Sass-Theming mit Variablen und Hooks](https://getuikit.com/docs/sass)
- [WCAG 2.2](https://www.w3.org/TR/WCAG22/)
- GitHub-Issue [#47: UIkit-Theme und Design-Token-Architektur validieren](https://github.com/STEImmo/STEImmo/issues/47)