# ADR-0003: Raumbezogene Prüfpunkte im Übergabeprotokoll

- Status: Accepted
- Datum: 2026-09-25
- Geltungsbereich: STEImmo-Django-Monolith

## Kontext

Das Übergabeprotokoll enthält feste Angaben wie Wohnung, Beteiligte, Zählerstände und Schlüssel. Die detaillierten Prüfpunkte unterscheiden sich jedoch nach Raum und können sich mit dem bisherigen Übergabebogen weiterentwickeln.

Ein rein festes Modell würde Änderungen am Bogen jeweils zu einer Schemaänderung machen. Zugleich müssen die bei einer Übergabe festgehaltenen Angaben nach der Bestätigung unverändert nachvollziehbar bleiben.

## Entscheidung

Feste Angaben des Deckblatts werden direkt am Modell `Protokoll` gespeichert. Räume werden als `Raumprotokoll` und ihre Prüfpunkte als `RaumMerkmal` mit der zugehörigen Bezeichnung `Merkmal` geführt. Damit können die Prüfpunkte des bisherigen Bogens raumbezogen und ohne neue Anwendungsschicht erfasst werden.

Schlüsselpositionen werden als `ProtokollSchluessel` im Protokoll gespeichert. Sie bilden den Bestand bei dieser konkreten Übergabe ab und verändern nicht den allgemeinen Schlüsselbestand der Wohnung.

Eine Bestätigung ist nur bei vollständigen Raumprüfpunkten und expliziten Erklärungen möglich. Danach erhält das Protokoll den Status `signed` und ist in der Oberfläche gegen Änderungen gesperrt.

## Konsequenzen

- Die Räume und Prüfpunkte des bisherigen Bogens können vollständig in ein konkretes Protokoll übertragen werden.
- Jedes bestätigte Protokoll behält seinen eigenen Prüf- und Schlüsselstand.
- Neue Prüfpunkte erfordern keine neue Datenbanktabelle oder JavaScript-Abhängigkeit.
- Nachträgliche Korrekturen an bestätigten Protokollen benötigen einen bewusst zu definierenden Korrekturprozess.
