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

Offene Zusagen werden vor den abgeschlossenen Vermietungen vollständig gelesen.
Für jede anschließend gelesene Vermietung entfällt die zugehörige offene Zusage.
So bleibt bei einem Abschluss zwischen den Abfragen mindestens eine der beiden
Anzeigen erhalten, ohne gleichzeitig eine offene und eine abgeschlossene
Vermietung für dieselbe Bewerbung auszugeben.

Vor der Mieterberechtigungsprüfung wird das Konto erneut geladen. So wird auch
eine beim ersten Abschluss zwischen Bewerberprüfung und Zusageabfrage neu
vergebene Mieterrolle berücksichtigt, ohne den vorherigen Berechtigungscache
weiterzuverwenden. Ein Regressionstest startet dafür mit einem reinen Bewerberkonto.

Der Wohnungsstatus wird aus dem bestehenden Wohnungsdatensatz gelesen. Spätere
Änderungen zu Verfügbar oder Gesperrt werden ebenfalls angezeigt; aus einem alten
Vermietungsabschluss wird nicht pauschal Vermietet abgeleitet. Vertragsbytes werden
weiterhin erst beim geschützten Download geladen.

Die Anzeige ändert keine fachlichen Status, erzeugt keine Vertragsunterzeichnung
und sendet keine zusätzlichen Nachrichten. Für die Anzeigen entstehen keine
neuen Tabellen oder fachlichen Schemaänderungen, JavaScript-Abhängigkeiten
oder zusätzliche UI-Komponentenbibliotheken.

## Prüfung

Django-Tests prüfen Zusage und Ablehnung, unvollständige oder beendete Bewerbungen,
den Übergang vom offenen zum abgeschlossenen Vermietungsablauf, erneute Anmeldung,
den aktuellen Wohnungsstatus, fremde Konten, Rollenentzug und Kontoneuverknüpfung
einschließlich einer Änderung während des Profilaufrufs.
Eine Gegenprobe schließt die Vermietung während der Seitenerstellung ab und
prüft, dass die Antwort keine widersprüchlichen Abschlussanzeigen enthält.
Regressionen decken sowohl einen Abschluss direkt nach dem Lesen offener Zusagen
als auch direkt nach dem Lesen abgeschlossener Vermietungen ab.

Die mit synthetischen Daten gerenderten HTML-Antworten wurden zusätzlich im
Browser bei 390 und 1280 Pixeln geprüft: Zusage im Profil, abgeschlossene
Vermietung, Bewerbungsübersicht, Hauptbewerbung und Profil ohne Zusage.
Die neuen Anzeigen bleiben lesbar und verursachen keinen horizontalen Überlauf.

## Integration mit main

Während der Umsetzung wurde #188 in main aufgenommen. Die leere Migration
`0038_merge_mail_settings_and_rental_completion` verbindet dessen Mail-Einstellungen
mit dem geprüften Vermietungszweig, ohne bereits geteilte Migrationen zu verändern.
Upgrade-Tests prüfen den Erhalt der Vertrags- und Kontozuordnungen sowie der
globalen Einstellungen, Mailadressen und Sperrzeit eines Testmailversuchs.

Vor dem PR wurde auch der inzwischen um #182 und #205 ergänzte main integriert.
Die zusätzliche leere Migration `0040_merge_notification_preferences_and_status_branch`
verbindet die bereits veröffentlichten Zweige, ohne sie nachträglich umzuschreiben.
Die Upgrade-Prüfung umfasst die Übernahme der alten globalen Abwahl sowie den
unveränderten Erhalt globaler Mailarten und persönlicher Benachrichtigungswahl.
Zusage, Wohnungskarte und Zugang zu den Benachrichtigungseinstellungen bleiben
gemeinsam im persönlichen Bereich verfügbar.

Bei der Review-Korrektur wurde main einschließlich Prozessbenachrichtigungen und
konkreter nächster Akteure integriert. Die leere Migration
`0041_merge_process_notifications_and_tenant_status` verbindet die beiden
veröffentlichten Migrationszweige. Die bestehenden Upgrade-Tests prüfen den
Datenerhalt bis zu diesem gemeinsamen Stand.

Nach Integration der Entscheidungsbenachrichtigungen aus #212 verbindet die leere
Migration `0042_merge_decision_notifications_and_tenant_status` deren Stand mit
dem Zusagezweig. Die Upgrade-Tests laufen bis zu diesem gemeinsamen Stand.

Nach den Merges von #203/#204 und #183 verbindet die leere Migration
`0044_merge_staff_digest_and_tenant_status` die Endpunkte
`0042_merge_decision_notifications_and_tenant_status` und `0043_staff_digest`.
Bereits veröffentlichte Migrationen bleiben unverändert. Die Upgrade-Tests
laufen bis zu diesem gemeinsamen Stand und prüfen aus beiden Zweigen den Erhalt
vorhandener Benachrichtigungen, persönlicher Einstellungen, des Zeitpunkts der
Erinnerungsauswahl und vorgemerkter Aufgaben der Tageszusammenfassung. Die
bestehenden Prüfungen für Verträge und Kontozuordnungen bleiben erhalten.
