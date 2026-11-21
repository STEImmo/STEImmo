# ADR-0026 Zusage und Vermietungsstatus im Konto

- Status: Angenommen
- Datum: 2026-11-21
- Issue: [#183](https://github.com/STEImmo/STEImmo/issues/183)

## Kontext

Die fachliche Annahme aus #180 und der Vermietungsabschluss aus #181/#182 sind
getrennte Schritte. Bisher blieb eine angenommene Bewerbung für den Nutzer als
eingereichte Hauptbewerbung sichtbar und forderte zum Warten auf eine Entscheidung
auf. Das Profil zeigte nach dem Abschluss Wohnung und Vertrag ohne Wohnungsstatus.

## Entscheidung

Die gemeinsame Statusanzeige einer angenommenen, eingereichten und weiterhin
offenen Bewerbung lautet **Als Mieter angenommen**. Zurückgezogene, abgelehnte,
gesperrte oder unvollständige Bewerbungen erhalten diese Anzeige auch dann nicht,
wenn ein alter Annahmezeitpunkt vorhanden ist. Die Bewerbungsübersicht und die
Hauptbewerbungsansicht verwenden denselben Zusagebaustein und zeigen keinen
überholten Hinweis auf eine noch ausstehende Entscheidung. Beide privaten
Ansichten unterbinden Browser-Caching.

Vor dem Vermietungsabschluss zeigt das eigene Profil die Zusage und den Hinweis,
dass der Abschluss noch aussteht. Voraussetzung sind der aktuelle Person-Konto-
Bezug und der Bewerberzugang. Auch wenn sich der Bezug während des Profilaufrufs
ändert, darf eine Zusage nicht an das bisherige Konto ausgegeben werden.

Nach dem Abschluss verwendet das Profil weiterhin die vorhandenen geschützten
Vermietungsdatensätze und Vertragslinks. Der Mieterzugang, das ursprüngliche
Mieterkonto und die weiterhin gültige Person-Konto-Verknüpfung sind gemeinsam
erforderlich. Eine manuelle Person-Wohnungszuordnung oder eine Mieterrolle allein
belegt keinen Vermietungsabschluss. Eine spätere Kontoverknüpfung überträgt weder
Wohnungsanzeige noch Vertrag automatisch.

Abgeschlossene Vermietungen werden vor der Ausgabe offener Zusagen gelesen.
Ein Abschluss während der Seitenerstellung darf keine gleichzeitig offene und
abgeschlossene Vermietung in derselben Antwort erzeugen.

Der Wohnungsstatus wird aus dem bestehenden Wohnungsdatensatz gelesen. Spätere
Änderungen zu Verfügbar oder Gesperrt werden ebenfalls angezeigt; aus einem alten
Vermietungsabschluss wird nicht pauschal Vermietet abgeleitet. Vertragsbytes werden
weiterhin erst beim geschützten Download geladen.

Die Anzeige ändert keine fachlichen Status, erzeugt keine Vertragsunterzeichnung
und sendet keine zusätzlichen Nachrichten. Es gibt keine neue Tabelle, Migration,
JavaScript-Abhängigkeit oder zusätzliche UI-Komponentenbibliothek.

## Prüfung

Django-Tests prüfen Zusage und Ablehnung, unvollständige oder beendete Bewerbungen,
den Übergang vom offenen zum abgeschlossenen Vermietungsablauf, erneute Anmeldung,
den aktuellen Wohnungsstatus, fremde Konten, Rollenentzug und Kontoneuverknüpfung
einschließlich einer Änderung während des Profilaufrufs.
Eine Gegenprobe schließt die Vermietung während der Seitenerstellung ab und
prüft, dass die Antwort keine widersprüchlichen Abschlussanzeigen enthält.

Die mit synthetischen Daten gerenderten HTML-Antworten wurden zusätzlich im
Browser bei 390 und 1280 Pixeln geprüft: Zusage im Profil, abgeschlossene
Vermietung, Bewerbungsübersicht, Hauptbewerbung und Profil ohne Zusage.
Die neuen Anzeigen bleiben lesbar und verursachen keinen horizontalen Überlauf.
