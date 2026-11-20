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
Die Bestätigung bindet Bewerbung, Person, Wohnung und Konto durch eine signierte
Formularangabe. Veraltete oder manipulierte Zuordnungen werden nicht übernommen;
bei einer Änderung sind erneute Prüfung und Dateiauswahl erforderlich. Nach der
PDF-Prüfung werden aktuelle Mitarbeiterrechte, Kontodaten und die bestehende
Sitzung erneut geprüft. Gleichzeitige Abschlüsse werden durch Zeilensperren
und eindeutige Datenbankbeziehungen auf einen Abschluss begrenzt.
Eine abweichende Wohnungszuordnung muss zuerst geklärt werden. Offene und
gesperrte Übergabeprotokolle blockieren eine Änderung der Wohnungszuordnung.

Je Bewerbung und Wohnung ist im aktuellen Ablauf ein Abschluss möglich.
Wiederholtes Ausführen behält die gespeicherte Zuordnung und Vertragsfassung.
Eine Beendigung mit anschließender Neuvermietung erfordert einen eigenen
fachlichen Ablauf. Der Wohnungsstatus wird mit #182 beim Abschluss gesetzt;
siehe [ADR-0025](0025-wohnungsstatus-beim-vermietungsabschluss.md).
Abgeschlossene Bewerbungen stehen in der allgemeinen Bewerbungsübersicht zur
Verfügung und werden im offenen Arbeitsablauf ausgeblendet.

Die PDF-Bytes werden mit dem Abschluss in PostgreSQL gespeichert, sodass
Zuordnung und Datei gemeinsam zurückgerollt werden können. Profillisten laden
die Datei erst beim Download. Der Download erfordert die Mieterrolle sowie
Übereinstimmung mit dem beim Abschluss gespeicherten und weiterhin mit der
Person verknüpften Konto. Ein späterer Kontowechsel überträgt den Vertrag nicht.
Die bisherigen Freigaberegeln für Übergabeprotokolle gelten auch für das
verknüpfte Mieterkonto.

## Prüfung

Nach Integration des gemergten #180 decken Django-Tests Abschluss und erneute
Anmeldung, unveränderte freigegebene Übergabeprotokolle, private Downloads,
ungültige PDFs, veränderte Konten und Wohnungen, Rechteentzug während der
Dateiprüfung, vollständigen Rollback und gleichzeitige Abschlussversuche ab.
Eine offene Übergabe blockiert eine neue Zuordnung weiterhin.

Am 20.11.2026 bestanden alle 1.013 Django-Tests auf PostgreSQL sowie
System-, Migrations- und Ruff-Prüfungen. Der interne Browser-Smoke-Test mit
isolierten synthetischen Daten bestätigte Abschluss, Abmeldung, erneute
Mieteranmeldung, Wohnungsanzeige und Download der bytegleichen Vertragsdatei.
