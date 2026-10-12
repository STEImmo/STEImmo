# ADR-0016: Bereinigung fehlgeschlagener Protokollarchive

- Status: Accepted
- Datum: 2026-10-07
- Bezug: #73; ergänzt ADR-0014

## Entscheidung

Neue private PDF- und Unterschriftsdateien werden vor dem ersten Schreibversuch
mit einem noch freien Speicherpfad erfasst. Gibt der Speicher einen abweichenden
Pfad zurück, wird auch dieser erfasst. Nach einem fehlgeschlagenen Abschluss
rollt zuerst die Archivtransaktion zurück. Anschließend wird für jeden erfassten
Pfad ein eindeutiger Auftrag in `HandoverArchiveCleanup` gespeichert, bevor die
Datei gelöscht wird. Erfolgreiche Löschungen entfernen ihren Auftrag.

Fehlgeschlagene Löschungen bleiben über Requests und Prozessneustarts hinweg
wiederholbar. `python manage.py retry_handover_archive_cleanup` bearbeitet die
persistierten Aufträge. Sofortige und wiederholte Bereinigung prüfen sowohl
`Protokoll.dokument_pfad` als auch `ProtokollUnterschrift.datei`; referenzierte
Dateien bleiben erhalten und der Auftrag meldet einen Fehler. Derselbe Ablauf
gilt für die nachträgliche Sicherung von Altprotokollen.

## Begründung und Konsequenzen

Eine reine Logmeldung genügt nicht, wenn Speicher oder Prozess während der
Bereinigung ausfallen. Die bestehende PostgreSQL-Datenbank und ein Django-
Managementbefehl reichen für den konkreten Wiederholungsbedarf aus; ein neuer
Dienst oder Hintergrund-Task-Framework wird nicht benötigt. Archivaufträge
bleiben von Fotoaufträgen getrennt, weil sie andere Dateireferenzen schützen.

Migration `0025` ergänzt nur die Auftragstabelle. Sie verändert weder bestehende
Archive noch bisherige Migrationen. Der Befehl findet ausschließlich registrierte
Dateien; ältere, bereits verwaiste Dateien werden nicht automatisch durchsucht.
Ist die Datenbank selbst für die Auftragserfassung nicht verfügbar, wird der
Fehler protokolliert; eine atomare Transaktion über Datenbank und Dateispeicher
steht weiterhin nicht zur Verfügung.
