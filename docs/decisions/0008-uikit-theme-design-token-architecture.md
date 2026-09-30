# ADR-0008: UIkit-Theme und Design-Token-Ablage

- Status: Proposed
- Datum: 2026-09-30
- Issue: #47 · Folgestories: #45 und #46

## Entscheidung

STEImmo baut das UI-Fundament mit der vorhandenen UIkit-Version und Django-Templates weiter. Semantische Design-Tokens und gezielte UIkit-Anpassungen liegen zunächst in `static/css/app.css`; die mitgelieferten Dateien unter `static/vendor/uikit/` bleiben unverändert. Tokens werden in `:root` mit einem `--steimmo-`-Präfix und semantischen Namen geführt, zum Beispiel `--steimmo-color-text`, `--steimmo-color-surface`, `--steimmo-color-action` und `--steimmo-focus-ring`. `templates/base.html` bleibt für den gemeinsamen Rahmen und die Navigation zuständig. App-übergreifende Template-Bausteine kommen bei tatsächlichem Wiederholungsbedarf nach `templates/partials/`; app-spezifische Partials bleiben in der jeweiligen App.

UIkit-Komponenten bleiben die Bausteine; die CSS-Custom-Properties benennen Projektwerte, und wenige gezielte Selektoren in `app.css` wenden sie auf genutzte UIkit-Komponenten an. Eigene CSS-Variablen allein ändern das bereits kompilierte UIkit-CSS nicht. Templates enthalten Struktur und Semantik; Partials kapseln nur tatsächlich wiederkehrendes Markup. UIkit-JavaScript genügt für UIkit-Interaktionen; Vanilla JavaScript kommt nur bei einem konkreten Bedarf dazu. Falls viele schwer wartbare CSS-Overrides nötig werden, wird UIkits Sass-Theming erneut geprüft. Ein zweites UI-Framework oder eine separate Frontend-Buildkette wird nicht eingeführt.

## Warum

Das Repository verwendet bereits Django-Templates und lokal eingebundenes UIkit. Die Lösung knüpft daran an, hält die Zahl der Werkzeuge klein und lässt die Farb- und Typografieentscheidungen in #45 offen. Es werden durch diese Entscheidung keine Datenmodelle, URLs, Berechtigungen oder fachlichen Abläufe geändert.

## Spike-Kriterien und Ergebnis

| Kriterium | Ergebnis |
|---|---|
| UIkit-Einbindung und Anpassbarkeit prüfen | `templates/base.html` lädt die versionierten UIkit-Dateien aus `static/vendor/uikit/` und `static/css/app.css`. Die vorhandene UIkit-CSS-Datei ist vorkompiliert; eigene Variablen greifen deshalb erst über Projektregeln. Gezielte CSS-Overrides sind jetzt schlank; Sass-Theming bleibt die Rückfalloption bei wachsendem Anpassungsbedarf. |
| Ablage und Benennung festlegen | Projekt-CSS und Tokens: `static/css/app.css`; Tokens in `:root` als `--steimmo-<bereich>-<bedeutung>` (etwa `--steimmo-color-text`). Theme-Regeln bleiben dort, Vendor-Dateien unverändert. |
| Zuständigkeiten abgrenzen | UIkit stellt Komponenten bereit; Custom Properties halten semantische Werte; gezielte CSS-Regeln verbinden beides; Django-Templates liefern Struktur; wiederkehrende app-übergreifende Partials liegen bei Bedarf in `templates/partials/`. UIkit-JS zuerst, Vanilla JS nur für notwendige projektspezifische Interaktion. |
| Öffentliche Seite und internes Dashboard skizzieren | Der Prototyp enthält eine öffentliche Formularvorschau und eine interne Dashboard-Skizze mit Navigation zu bestehenden Bereichen sowie eine Beispiel-Wohnungsliste. Die interne Übersichtsroute existiert im Produkt derzeit nicht; die Dashboard-Karten sind daher nur ein Navigationsmuster. |
| Responsivität, Fokus, Validierung und Zustände bewerten | Öffentliche Ansicht: Formular stapelt auf schmalen Ansichten; Labels bleiben sichtbar; ein statischer ungültiger E-Mail-Zustand ist mit `aria-invalid` und `aria-describedby` dem Feld zugeordnet; Fokus ist über einen deutlichen Ring sichtbar. Dashboard/Liste: Karten stapeln, Navigation bleibt umbrechend erreichbar, Tabellenwerte erhalten Mobilbeschriftungen, Status zeigt Text plus Symbol/Farbe. Das Dashboard hat bewusst kein Formular; Validierung wird am öffentlichen Formularmuster beurteilt. Dies ist eine konzeptionelle Bewertung, keine Browser-/Assistive-Technology-Abnahme der Produktseiten; die konkrete Umsetzung wird in #45/#46 geprüft. |

## Wozu die Skizze dient

Die [statische Skizze](../prototypes/47-corporate-design-prototype.html) übersetzt diese Architekturentscheidung in sichtbare Beispiele. An Formular, Navigation und Wohnungsliste lässt sich besprechen, wie „vorhandenes UIkit + Projekt-CSS + Django-Templates“ für STEImmo wirken und auf schmalen Ansichten funktionieren kann. So können Auftraggeber und Team die Richtung beurteilen, bevor #45 die Tokens und #46 die wiederverwendbaren UI-Muster in den echten Seiten umsetzen.

Die Skizze ist damit ein gemeinsamer Gesprächs- und Prüfgegenstand für den Spike: Sie zeigt eine mögliche Anwendung der Entscheidung, macht offene Designfragen sichtbar und liefert konkrete Anknüpfungspunkte für die Folgestories. Sie ist weder ein fertiges Design noch eine neue Produktseite; Beispielwerte und Navigationslinks sind nicht funktional. Sie verändert keine bestehenden Abläufe. Das Haussymbol ist ein ausdrücklich markierter Platzhalter, bis das Element vom Briefkopf vorliegt.

Der Prototyp lädt das vorhandene UIkit-CSS direkt. Die vom Auftraggeber genannten Fassadenfarben sind Kandidaten, keine freigegebene Palette. Im Prototyp dienen Sand `#DFD7CE` und Anthrazit `#3F4345` als erste Flächen-/Textkombination. Taupe `#AB9F94` und Sockelgrau `#89847A` sind wegen ihres geringen Kontrasts auf Sand nur dekorative Akzente. Die Kombination Sand/Anthrazit erreicht rund 7:1; Farben, Fokus und Zustände sind bei #45/#46 an den echten Seiten abschließend zu prüfen. Für normalen Text gilt WCAG-AA-Kontrast von mindestens 4,5:1.

Codebefunde, die #45/#46 berücksichtigen sollten: Die Navbar hat noch keinen mobilen Menüschalter; die Wohnungsliste ist derzeit horizontal scrollbar; bei UIkits responsiver Tabelle müssen Zellbezeichnungen auf schmalen Ansichten sichtbar bleiben. Die vorhandene Verwaltungsroute ist eine Liste, kein Dashboard.

## Verworfen

- Zweites UI-Framework oder separate Frontend-Anwendung: doppelte Komponenten- und Wartungsbasis.
- Änderungen an `static/vendor/uikit/`: vermischt Projektgestaltung mit Drittanbieterdateien.
- Sass-Neukompilierung sofort: derzeit unverhältnismäßige zusätzliche Toolchain; neu bewerten, falls gezielte Overrides ausufern.
- Globale Partials ohne nachgewiesene Wiederverwendung: unnötige Abstraktion.

## Referenzen

- [UIkit: Sass-Theming](https://getuikit.com/docs/sass)
- [WCAG 2.2, Kontrastminimum](https://www.w3.org/TR/WCAG22/#contrast-minimum)
- [Issue #47](https://github.com/STEImmo/STEImmo/issues/47)
