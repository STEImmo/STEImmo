# ADR-0008: UIkit-Theme und Design-Token-Ablage

- Status: Proposed
- Datum: 2026-09-30
- Issue: #47 · Folgestories: #45 und #46

## Entscheidung

STEImmo baut das UI-Fundament mit der vorhandenen UIkit-Version und Django-Templates weiter. Semantische Design-Tokens und gezielte UIkit-Anpassungen liegen zunächst in `static/css/app.css`; die mitgelieferten Dateien unter `static/vendor/uikit/` bleiben unverändert. `templates/base.html` bleibt für den gemeinsamen Rahmen und die Navigation zuständig. App-übergreifende Template-Bausteine kommen bei tatsächlichem Wiederholungsbedarf nach `templates/partials/`; app-spezifische Partials bleiben in der jeweiligen App.

Für UIkit-Komponenten nutzt die Projekt-CSS wenige gezielte Selektoren. Eigene CSS-Variablen allein ändern das bereits kompilierte UIkit-CSS nicht. Falls viele schwer wartbare Overrides nötig werden, wird UIkits Sass-Theming erneut geprüft. UIkit-JavaScript und bei konkretem Bedarf Vanilla JavaScript genügen; ein zweites UI-Framework oder eine separate Frontend-Buildkette wird nicht eingeführt.

## Warum

Das Repository verwendet bereits Django-Templates und lokal eingebundenes UIkit. Die Lösung knüpft daran an, hält die Zahl der Werkzeuge klein und lässt die Farb- und Typografieentscheidungen in #45 offen. Es werden durch diese Entscheidung keine Datenmodelle, URLs, Berechtigungen oder fachlichen Abläufe geändert.

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
