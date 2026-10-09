# ADR-0008: UIkit-Theme und Design-Token-Ablage

- Status: Accepted
- Datum: 2026-09-30
- Issue: #47 · Folgestories: #45 und #46

## Entscheidung

STEImmo baut das UI-Fundament mit der vorhandenen UIkit-Version und Django-Templates weiter. Semantische Design-Tokens und gezielte UIkit-Anpassungen liegen zunächst in `static/css/app.css`; die mitgelieferten Dateien unter `static/vendor/uikit/` bleiben unverändert. Tokens werden in `:root` mit einem `--steimmo-`-Präfix und semantischen Namen geführt, zum Beispiel `--steimmo-color-text`, `--steimmo-color-surface`, `--steimmo-color-action` und `--steimmo-focus-ring`. `templates/base.html` bleibt für den gemeinsamen Rahmen und die Navigation zuständig. App-übergreifende Template-Bausteine kommen bei tatsächlichem Wiederholungsbedarf nach `templates/partials/`; app-spezifische Partials bleiben in der jeweiligen App.

UIkit-Komponenten bleiben die Bausteine; die CSS-Custom-Properties benennen Projektwerte, und wenige gezielte Selektoren in `app.css` wenden sie auf genutzte UIkit-Komponenten an. Eigene CSS-Variablen allein ändern das bereits kompilierte UIkit-CSS nicht. Templates enthalten Struktur und Semantik; Partials kapseln nur tatsächlich wiederkehrendes Markup. UIkit-JavaScript genügt für UIkit-Interaktionen; Vanilla JavaScript kommt nur bei einem konkreten Bedarf dazu. Falls viele schwer wartbare CSS-Overrides nötig werden, wird UIkits Sass-Theming erneut geprüft. Ein zweites UI-Framework oder eine separate Frontend-Buildkette wird nicht eingeführt.

## Verbindliche Theme-Regeln aus #45

Die Umsetzung bestätigt die Token-Ablage in static/css/app.css und bindet die vorhandene, vorkompilierte UIkit-Version 3.25.24 gezielt daran. Die Vendor-Dateien bleiben unverändert. Projekt-Templates erhalten keine verteilten Farbwerte; Farben werden zentral als semantische Custom Properties definiert.

| Semantische Rolle | Token | Festgelegter Wert |
|---|---|---|
| Primäraktion | --steimmo-color-primary | Waldgrün #2D5A43 |
| Sekundäraktion | --steimmo-color-action-secondary | Anthrazit #3F4345; als neutrale, umrandete UIkit-Standardaktion |
| Text und ruhige Flächen | --steimmo-color-text, --steimmo-color-text-muted, --steimmo-color-surface, --steimmo-color-surface-page, --steimmo-color-surface-brand | #292B2C, #595959, #FFFFFF, #F5F2EF, #DFD7CE |
| Erfolg | --steimmo-color-success, --steimmo-color-success-text, --steimmo-color-success-surface | #2D6A4F, #205735, #EAF4EC |
| Warnung | --steimmo-color-warning, --steimmo-color-warning-text, --steimmo-color-warning-surface | #825000, #5E3A00, #FFF3D6 |
| Fehler/Gefahr | --steimmo-color-danger, --steimmo-color-danger-text, --steimmo-color-danger-surface | #922222, #922222, #FDECEC |
| Information | --steimmo-color-info, --steimmo-color-info-surface | #174957, #EAF3F5 |
| Fokus | --steimmo-color-focus-ring, --steimmo-color-focus-ring-inverse | #155EEF auf hellen Flächen einschließlich des Außenrings von Aktionsbuttons, #FFFFFF auf dunkler Navigation |
| Deaktiviert | --steimmo-color-disabled-text, --steimmo-color-disabled-surface, --steimmo-color-disabled-border | #595959, #ECEAE6, #C9C4BE |

Typografie verwendet den Systemschrift-Stack, eine Skala von 0.75rem bis 2.5rem und Zeilenhöhen von 1.25, 1.5 und 1.65. Spacing reicht in einer kleinen Skala von 0.25rem bis 3rem. Radien sind 4px, 8px, 10px und pillenförmig; Karten und Dialoge verwenden zentrale kleine und mittlere Schatten. Diese Werte liegen ebenfalls als --steimmo- Tokens in app.css.

Die gezielten UIkit-Zuordnungen setzen Primary-Buttons auf Waldgrün, Default-Buttons als umrandete Sekundäraktion, Danger-Buttons auf ein dunkles Rot und deaktivierte Controls auf gut erkennbare neutrale Werte. Links, Formfelder, Checkboxen und Radiobuttons, Validierungsfarben, Info-/Success-/Warning-/Danger-Alerts, Labels/Badges, Cards, Navigation, Tabellen und Listen verwenden dieselben Tokens. Hover-, Active-, Disabled- und Focus-visible-Zustände sind explizit gestaltet. Statusbegriffe und Fehlertexte bleiben erhalten; Farbe ergänzt den Text und ersetzt ihn nicht. Die vorhandene wiederverwendete Formular-Partial bleibt zuständig; #45 führt keine künstlichen neuen Partials ein.

Die Kontrastwerte wurden mit der relativen Luminanzformel aus WCAG 2.2 geprüft. Weiß auf der Primäraktion erreicht 7.91:1, Waldgrün auf der Fassadenfläche 5.55:1, Haupttext auf Weiß 14.23:1, zurückhaltender Text auf der Fassadenfläche 4.92:1. Success-Labeltext auf Success-Grün erreicht 6.39:1; Success-Alerttext 7.53:1; Warning-Alerttext 9.15:1; Danger-Labeltext 8.49:1; Danger-Alerttext 7.43:1; Infotext 8.76:1. Die stärkere Eingabefeldgrenze erreicht auf Weiß 4.81:1 und auf Sand 3.38:1. Der blaue Fokusring erreicht auf Weiß 5.41:1 und auf Sand 3.80:1; auf der dunklen Navbar wird ein weißer Fokusring mit 10.00:1 verwendet. Deaktivierter Text bleibt mit 5.83:1 auf seiner neutralen Fläche ebenfalls gut erkennbar.

## Warum

Das Repository verwendet bereits Django-Templates und lokal eingebundenes UIkit. Die Lösung knüpft daran an, hält die Zahl der Werkzeuge klein und konkretisiert in #45 die abschließenden Farb- und Typografieentscheidungen. Es werden durch diese Entscheidung keine Datenmodelle, URLs, Berechtigungen oder fachlichen Abläufe geändert.

## Spike-Kriterien und Ergebnis

| Kriterium | Ergebnis |
|---|---|
| UIkit-Einbindung und Anpassbarkeit prüfen | `templates/base.html` lädt die versionierten UIkit-Dateien aus `static/vendor/uikit/` und `static/css/app.css`. Die vorhandene UIkit-CSS-Datei ist vorkompiliert; eigene Variablen greifen deshalb erst über Projektregeln. Gezielte CSS-Overrides sind jetzt schlank; Sass-Theming bleibt die Rückfalloption bei wachsendem Anpassungsbedarf. |
| Ablage und Benennung festlegen | Projekt-CSS und Tokens: `static/css/app.css`; Tokens in `:root` als `--steimmo-<bereich>-<bedeutung>` (etwa `--steimmo-color-text`). Theme-Regeln bleiben dort, Vendor-Dateien unverändert. |
| Zuständigkeiten abgrenzen | UIkit stellt Komponenten bereit; Custom Properties halten semantische Werte; gezielte CSS-Regeln verbinden beides; Django-Templates liefern Struktur; wiederkehrende app-übergreifende Partials liegen bei Bedarf in `templates/partials/`. UIkit-JS zuerst, Vanilla JS nur für notwendige projektspezifische Interaktion. |
| Öffentliche Seite und internes Dashboard skizzieren | Der Prototyp enthält eine öffentliche Formularvorschau und eine interne Dashboard-Skizze mit Navigation zu bestehenden Bereichen sowie eine Beispiel-Wohnungsliste. Seit dem Spike ergänzt PR #62 die interne Bewerbungsübersicht je Wohnung mit Filter, Pagination und Detailansicht; eine allgemeine Verwaltungsübersichtsroute gibt es weiterhin nicht. |
| Responsivität, Fokus, Validierung und Zustände bewerten | Öffentliche Ansicht: Formular stapelt auf schmalen Ansichten; Labels bleiben sichtbar; ein statischer ungültiger E-Mail-Zustand ist mit `aria-invalid` und `aria-describedby` dem Feld zugeordnet; Fokus ist über einen deutlichen Ring sichtbar. Dashboard/Liste: Karten stapeln, Navigation bleibt umbrechend erreichbar, Tabellenwerte erhalten Mobilbeschriftungen, Status zeigt Text plus Symbol/Farbe. Das Dashboard hat bewusst kein Formular; Validierung wird am öffentlichen Formularmuster beurteilt. Dies ist eine konzeptionelle Bewertung, keine Browser-/Assistive-Technology-Abnahme der Produktseiten; die konkrete Umsetzung wird in #45/#46 geprüft. |

## Wozu die Skizze dient

Die [statische Skizze](../prototypes/47-corporate-design-prototype.html) übersetzt diese Architekturentscheidung in sichtbare Beispiele. An Formular, Navigation und Wohnungsliste lässt sich besprechen, wie „vorhandenes UIkit + Projekt-CSS + Django-Templates“ für STEImmo wirken und auf schmalen Ansichten funktionieren kann. So konnten Auftraggeber und Team die Richtung beurteilen; #45 setzt das Theme auf den Produktseiten um, #46 vereinheitlicht die umfassenden UI-Muster.

Die Skizze ist damit ein gemeinsamer Gesprächs- und Prüfgegenstand für den Spike: Sie zeigt eine mögliche Anwendung der Entscheidung, macht offene Designfragen sichtbar und liefert konkrete Anknüpfungspunkte für die Folgestories. Sie ist weder ein fertiges Design noch eine neue Produktseite; Beispielwerte und Navigationslinks sind nicht funktional. Sie verändert keine bestehenden Abläufe. Das Haussymbol ist ein ausdrücklich markierter Platzhalter, bis das Element vom Briefkopf vorliegt.

Der Prototyp lädt das vorhandene UIkit-CSS direkt. Die vom Auftraggeber genannten Fassadenfarben sind Kandidaten, keine freigegebene Palette. Im Prototyp dienen Sand `#DFD7CE` und Anthrazit `#3F4345` als erste Flächen-/Textkombination. Taupe `#AB9F94` und Sockelgrau `#89847A` sind wegen ihres geringen Kontrasts auf Sand nur dekorative Akzente. Waldgrün `#2D5A43` und Petrol `#1F4E5B` werden als zwei mögliche Akzentrichtungen nebeneinander gezeigt, ohne sie schon fest zuzuweisen. Beide sind benachbarte Blaugrüntöne (analog/harmonisch, keine Komplementärfarben) und passen zu den warmen Fassaden-Neutralen. Waldgrün wirkt erdiger; Petrol kühler und urbaner. Weißer Text erreicht 7,9:1 auf Waldgrün bzw. 9,1:1 auf Petrol; auf Sand liegen die Farben bei 5,6:1 bzw. 6,4:1. Beide erfüllen damit WCAG-AA für normalen Text auf Sand. Die Skizze zeigt hierfür reine Farbflächen statt zusätzlicher Beispielbuttons; #45 wählt Waldgrün als Primärfarbe. Statusfarben bleiben semantisch getrennt von Marken- und CTA-Farben und werden zusätzlich durch Text bezeichnet. #45 prüft Farben, Fokus und Zustände an den echten Seiten; #46 übernimmt die umfassenden UI-Muster.

Codebefunde für #46: Die gemeinsame Navbar hat noch keinen mobilen Menüschalter. Die interne Bewerbungsübersicht (#62) nutzt für Tabellen horizontalen Überlauf mit fokussierbarer Region; ein konsistentes mobiles Tabellenmuster sollte in #46 geprüft werden. Die allgemeine Verwaltungsroute bleibt eine Liste, kein separates Dashboard.

## Verworfen

- Zweites UI-Framework oder separate Frontend-Anwendung: doppelte Komponenten- und Wartungsbasis.
- Änderungen an `static/vendor/uikit/`: vermischt Projektgestaltung mit Drittanbieterdateien.
- Sass-Neukompilierung sofort: derzeit unverhältnismäßige zusätzliche Toolchain; neu bewerten, falls gezielte Overrides ausufern.
- Globale Partials ohne nachgewiesene Wiederverwendung: unnötige Abstraktion.

## Referenzen

- [UIkit: Sass-Theming](https://getuikit.com/docs/sass)
- [WCAG 2.2, Kontrastminimum](https://www.w3.org/TR/WCAG22/#contrast-minimum)
- [Issue #47](https://github.com/STEImmo/STEImmo/issues/47)
