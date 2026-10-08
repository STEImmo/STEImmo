# ADR-0013: Verifizierte Foto-Typen und eindeutige Prüfpunkte

## Kontext

Prüfpunktfotos werden über Django ausgeliefert und beim Auszug über Raum und
Merkmal dem Einzugszustand gegenübergestellt. Der vom Browser gelieferte
MIME-Typ ist dabei nicht vertrauenswürdig. Außerdem waren dieselben
Raum-/Merkmal-Kombinationen in einem Raumprotokoll mehrfach möglich, wodurch
der Alt/Neu-Vergleich einen Eintrag stillschweigend überschreiben konnte.

## Entscheidung

JPEG, PNG und WebP werden weiterhin mit `ImageField` inhaltlich geprüft. Der
gespeicherte und ausgelieferte MIME-Typ wird ausschließlich aus dem von Pillow
verifizierten Bildformat abgeleitet. Auch historische Bilddateien werden beim
Abruf erneut geprüft und nur mit einem festen erlaubten Bildtyp ausgeliefert.

Die Mitarbeiterberechtigung schützt einheitlich die Foto-Oberfläche,
Einzugsreferenzen sowie Upload-, Anzeige- und Lösch-Endpunkte.
Damit ersetzt diese Entscheidung die staff-spezifische Schutzbeschreibung aus
ADR-0009.

Ein Raumprotokoll darf pro Merkmal nur einen Prüfpunkt enthalten. Die
Eingabeformulare zeigen bei einer doppelten Kombination eine Feldfehlermeldung.
Eine Datenbank-Constraint sichert diese Regel für alle Schreibwege. Die
Migration beendet sich mit einem konkreten Hinweis, falls historische Daten
Dubletten enthalten; Belegfotos werden nicht automatisch gelöscht.

### Speicherfehler bei Foto-Uploads (Issue #65)

Dateisystem-Schreibvorgänge werden durch eine Datenbanktransaktion nicht
zurückgerollt. Beide Uploadwege, einschließlich Fotos im Protokollformular,
verfolgen deshalb die neu erzeugten UUID-Dateinamen vor dem ersten Schreibversuch
und gegebenenfalls einen abweichenden vom Storage zurückgegebenen Namen.
Ein fehlgeschlagener Upload rollt Protokoll-, Prüfpunkt- und Fotoänderungen
zurück und bereinigt ausschließlich diese neuen Dateien. Das gilt auch, wenn
der Storage erst nach dem Schreiben einen Fehler meldet oder die Speicherung
eines Datenbankeintrags scheitert. Vorhandene Fotos bleiben erhalten.

Nach dem Datenbank-Rollback werden Bereinigungsaufträge in
`HandoverPhotoCleanup` angelegt und sofort abgearbeitet. Ein fehlgeschlagener
Löschversuch erhält den Auftrag für den Management-Command
`retry_handover_photo_cleanup`. Dieser verwendet denselben Foto-Storage und
löscht keine weiterhin von einem Foto referenzierte Datei. Die zusätzliche
Tabelle wird durch eine neue additive Migration angelegt; bestehende
Migrationen werden nicht verändert. Eine neue Runtime-Abhängigkeit oder ein
Hintergrunddienst ist dafür nicht erforderlich. Die Aufträge enthalten nur
zufällig erzeugte Dateinamen, keine Dokumentinhalte oder Originalnamen.

Die Oberfläche erklärt den fehlgeschlagenen Upload und bittet um erneute
Fotoauswahl. Protokollentwürfe werden erst bei erfolgreicher Speicherung
entfernt. Fehlermeldungen im Log nennen die Fehlerklasse, keine Dateiinhalte
oder vom Storage gelieferten Detailmeldungen.

### Bereinigung entfernter Fotos (Issue #67)

Auch beim Entfernen vorhandener Fotos wird `HandoverPhotoCleanup` verwendet.
Bereinigungsauftrag und Entfernung der Foto-Referenz erfolgen in derselben
Datenbanktransaktion. Erst nach erfolgreichem Commit beginnt die Dateilöschung.
Eine Ausnahme wird kontrolliert protokolliert und lässt den Auftrag für den
bestehenden Wiederholungsbefehl erhalten. Weitere Bereinigungen können fortfahren.
Bei einem Rollback bleiben Datei und Fotoeintrag erhalten; der Lösch-Callback
wird verworfen. Noch referenzierte Dateien werden auch beim sofortigen
Bereinigungsversuch geschützt. Es ist keine neue Tabelle oder Abhängigkeit nötig.

### Validierung nach endgültiger Raumzuordnung (Issue #66)

Mehrere Prüfpunktzeilen dürfen den Raum aus der vorherigen Zeile übernehmen.
Das Formset löst zuerst diese endgültige Zuordnung auf und prüft danach den
betroffenen vorhandenen Prüfpunkt, Kollisionen und die gemeinsame Anzahl
vorhandener und neuer Fotos. Eine Prüfung nur im einzelnen Formular würde bei
noch leerem Raum die Fotos eines passenden vorhandenen Prüfpunkts übersehen.
Dies gilt ebenso für unterstützte ältere Entwürfe ohne Prüfpunkt-ID.
Fehlerhafte Zeilen werden nicht zur weiteren Prüfung oder Speicherung verwendet.
Die zulässige Fotoanzahl und das Datenmodell bleiben unverändert.

## Konsequenzen

- Client-seitig deklarierte Typen können nicht mehr zur HTML-Auslieferung von
  Bilddateien führen.
- Mitarbeiter erhalten die gleiche Foto-Bedienung, die ihre geschützten
  Endpunkte erlauben.
- Alt/Neu-Referenzen bleiben eindeutig; vorhandene Daten werden nicht
  stillschweigend verändert.
