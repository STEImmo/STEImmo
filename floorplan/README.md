# STEImmo-Floorplan

Interaktive Architekturübersicht des Repository-Stands `1ffab96`, erstellt mit [Floorplan](https://github.com/haydenschmitty/floorplan).

- `steimmo-map.html`: eigenständige Karte zum Öffnen im Browser, auch ohne laufenden Server.
- `STEImmo-Architektur-Floorplan-5K.png`: Screenshot der Übersicht für Präsentationen (5120 × 2880 Pixel).
- `architecture.json` und `descriptions/`: bearbeitbare Gliederung und Beschreibungen.
- `index.html`, `graph.json` und die `.mjs`-Dateien: erzeugte Karte und zugehörige Hilfsprogramme.

Die Karte lässt sich bei installiertem Floorplan-Skill durch einen erneuten Build aktualisieren. Floorplan schließt das Verzeichnis normalerweise von Git aus und weist bei bereits versionierten Dateien darauf hin; diese Dateien sind hier bewusst versioniert. Der lokale Cache unter `.cache/` gehört nicht ins Repository.

Die automatische Routenerkennung kürzt einige verschachtelte Profiladressen und erfasst eine Testadresse; Hinweise stehen an den betreffenden Stellen der Karte. Die automatischen Secret-Warnungen betreffen Testpasswörter und das veröffentlichte Passwort eines Entwicklungskontos; sie sind keine bestätigten Produktionszugänge.
