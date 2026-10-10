# ADR-0017: Kontrast des Foto- und Entwurfhinweises

- Status: Angenommen
- Datum: 2026-10-10
- Issue: [#113](https://github.com/STEImmo/STEImmo/issues/113)

## Kontext

Im QA-Stand von Issue #113 verwendete der Hinweis zu Bildformaten,
8-MiB-Limit und fehlender Foto-Zwischenspeicherung UIkits `uk-text-meta`:
14-Pixel-Text in `#999999` auf Weiß erreichte 2,85:1.
[WCAG 2.2, Kriterium 1.4.3](https://www.w3.org/WAI/WCAG22/Understanding/contrast-minimum.html)
verlangt für diesen Text mindestens 4,5:1.

Auf dem aktuellen `main` erhöht das Projekt-Theme den Metatext-Kontrast bereits.
Dieser Fix gestaltet den wesentlichen Hinweis ausdrücklich mit der dunklen
UIkit-Textfarbe und vereinheitlicht seine drei Ausgabewege.

## Entscheidung

Der Hinweis verwendet `uk-text-small` für die bisherige Textgröße und
`uk-text-emphasis` für UIkits dunkle Textfarbe (`#333333`). Auf Weiß erreicht
sie 12,63:1, auf der aktuellen Theme-Fläche `#EEEBE7` 10,63:1.
Das gemeinsame Partial `_handover_photo_upload_hint.html` wird
für bestehende Prüfpunkte und die Vorlagen für zusätzliche Räume und
Prüfpunkte eingebunden.

## Konsequenzen und Alternativen

Der Hinweis bleibt an derselben Stelle und bricht auf schmalen Ansichten um.
Ein eigener CSS-Farbwert ist unnötig, da UIkit eine passende Textfarbe
bereitstellt. Eine globale Änderung von `uk-text-meta` würde weitere,
außerhalb dieses Issues liegende Elemente verändern. Die gemeinsame Vorlage
verhindert, dass die drei Ausgabewege bei späteren Änderungen auseinanderlaufen.
