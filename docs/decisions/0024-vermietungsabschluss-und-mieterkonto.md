# ADR-0024 Vermietungsabschluss und Mieterkonto

- Status: Angenommen
- Datum: 2026-11-18
- Issue: [#181](https://github.com/STEImmo/STEImmo/issues/181)

## Kontext

Die bisherige Bewerbungsannahme versendet ein PDF per E-Mail. Die manuelle
Person-Wohnungszuordnung und die Verwaltung der Kontorollen sind separate
Schritte. In der Bewerbungsdetailansicht fehlte ein Abschluss, der die Zuordnung
speichert und die endgültige Vertragsfassung im Mieterkonto bereitstellt.

## Entscheidung

Mitarbeitende bestätigen in der angenommenen Hauptbewerbung das verknüpfte,
aktive Benutzerkonto und laden die endgültige Vertragsfassung als PDF hoch.
Für das PDF gilt das bestehende Limit von 5 MiB. Dateiprüfung und Upload erfolgen
vor dem Speichern. Vertragsdaten, Person-Wohnungszuordnung und die zusätzliche
Mieterrolle werden gemeinsam in einer Datenbanktransaktion gespeichert.
Eine abweichende Wohnungszuordnung muss zuerst geklärt werden. Offene und
gesperrte Übergabeprotokolle blockieren eine Änderung der Wohnungszuordnung.

Je Bewerbung und Wohnung ist im aktuellen Ablauf ein Abschluss möglich.
Wiederholtes Ausführen behält die gespeicherte Zuordnung und Vertragsfassung.
Eine Beendigung mit anschließender Neuvermietung erfordert einen eigenen
fachlichen Ablauf. Der Wohnungsstatus folgt in #182.
Abgeschlossene Bewerbungen stehen in der allgemeinen Bewerbungsübersicht zur
Verfügung und werden im offenen Arbeitsablauf ausgeblendet.

Die PDF-Bytes werden mit dem Abschluss in PostgreSQL gespeichert, sodass
Zuordnung und Datei gemeinsam zurückgerollt werden können. Profillisten laden
die Datei erst beim Download. Der Download erfordert die Mieterrolle sowie
Übereinstimmung mit dem beim Abschluss gespeicherten und weiterhin mit der
Person verknüpften Konto. Ein späterer Kontowechsel überträgt den Vertrag nicht.
Die bisherigen Freigaberegeln für Übergabeprotokolle gelten auch für das
verknüpfte Mieterkonto.
