# ADR-0014: PDF-Archiv und Touch-Unterschriften für Übergaben

- Status: Accepted
- Datum: 2026-10-02
- Bezug: US-11, Issue #25; ergänzt ADR-0008, ADR-0010 und ADR-0012

## Entscheidung

Mitarbeiter und Mieter unterschreiben beim Termin auf demselben Gerät in der
angemeldeten Mitarbeitersitzung. Die Mitarbeiterunterschrift ist erforderlich.
Für den Mieter wird entweder eine Unterschrift oder eine ausdrücklich gewählte,
nicht leere Begründung mit höchstens 1.000 Zeichen erfasst. Ein Mieterkonto ist
zum Unterschreiben nicht notwendig. Die Bilder dokumentieren diese gemeinsame
Erfassung; sie sind keine separate Anmeldung oder Identitätsprüfung des Mieters.

Die Unternehmensvertretung entspricht dem angemeldeten Mitarbeiterprofil und
ist im Formular nicht separat auswählbar. Übersicht, Abschluss und PDF verwenden
denselben Namen; beim Abschluss wird er zusammen mit der Unterschrift eingefroren.
Prüfpunkte erfassen neue Angaben im Feststellungstext. Die gesonderten dynamischen
Zusatzfelder entfallen; bereits gespeicherte Zusatzangaben bleiben erhalten.
Ein gemeinsames UIkit-Partial bietet Foto-Icon, Mehrfachauswahl und lokale Vorschau.
Weitere Auswahlen ergänzen die vorhandene Auswahl; einzelne ausgewählte Bilder
können vor dem Speichern entfernt werden. Erst das Speichern überträgt die Dateien.

Der Abschlussbildschirm zeigt genau die für das PDF verwendeten Daten, Fotos und
Einzugsreferenzen. Ein signierter Inhaltsfingerprint bindet die Bestätigung an
diesen Stand und das Mitarbeiterkonto. Bei Änderungen ist eine erneute Prüfung
und Unterzeichnung notwendig. Alle Protokoll-Schreibansichten und der Abschluss
sperren dieselbe Protokollzeile innerhalb einer Transaktion.

Die Zeichenflächen nutzen Canvas und Pointer Events mit Vanilla JavaScript;
UIkit bleibt das einzige UI-Framework. Finger, Stift und Maus werden unterstützt.
Eine feste Zeichenauflösung erhält die Eingabe bei Größenänderungen. Nur das
Zeichenfeld unterbindet Scrollgesten. Unterschriften bleiben bis zum Abschluss
im Arbeitsspeicher der geöffneten Seite, niemals im allgemeinen Entwurf oder
Local Storage. Bei Übertragungsfehlern bleiben sie auf dieser Seite erhalten.

Der Server akzeptiert nur nicht leere PNGs mit 1.200 × 400 Pixeln und höchstens
512 KiB pro Unterschrift. Pillow dekodiert und normalisiert sie. Name, Rolle,
Prüfsumme und gemeinsamer serverseitiger Erfassungszeitpunkt werden gespeichert.
Der Erfassungszeitpunkt bezeichnet den Abschluss, nicht einen behaupteten
einzelnen Zeichenzeitpunkt. Eine fehlende Mieterunterschrift mit Begründung wird
im PDF ausdrücklich ausgewiesen.

ReportLab (BSD-Lizenz) erzeugt innerhalb des Monolithen das PDF einschließlich
eingebetteter Bilder und der mitgelieferten Bitstream-Vera-Schrift. Der konkrete
MVP-Nutzen sind kontrollierte Seitenumbrüche und portable PDF-Erzeugung ohne
Browserprozess oder zusätzlichen Dienst. `pypdf` (BSD-Lizenz) ist ausschließlich
eine Entwicklungsabhängigkeit zur Prüfung der exportierten Inhalte. Beide
Abhängigkeiten sind auf ihre jeweilige Hauptversion begrenzt; Updates erfolgen
mit Tests und Sichtprüfung. Es werden keine externen Ressourcen geladen.

Snapshot, Unterschriften und PDF werden beim Abschluss gespeichert. Erst danach
wird der bestätigte Status übernommen; Speicherfehler rollen die Datenbank zurück
und räumen neu angelegte Dateien auf. Die bestehenden Dokumentpfad- und
SHA-256-Felder werden wiederverwendet. Spätere Downloads lesen die archivierten
Bytes und prüfen ihre Integrität. Es gibt keine stille Neuerzeugung bei einem
fehlenden oder beschädigten Archiv. Datenbank und Media-Volume sind gemeinsam
zu sichern; `private/` im Media-Storage darf nicht direkt vom Webserver bedient
werden. Die Anwendung veröffentlicht hierfür keine Media-Routen.

Altprotokolle können per ausdrücklichem POST einmalig nachträglich archiviert
werden. Der Export nennt beide Zeitpunkte sowie nicht rekonstruierbare
Stammdatenänderungen und fehlende historische Unterschriften. Eine Unterschrift
wird nie rückwirkend in eine bereits bestätigte Fassung eingesetzt.

Mitarbeiter dürfen alle bestätigten Protokolle exportieren. Mieter benötigen das
Mieterbereichsrecht und die Zuordnung über `Protokoll.person.user`. Eine aktuelle
Wohnungszuordnung gewährt keinen Zugriff auf frühere Bewohner. Die persönlichen
Downloads erweitern weder Bearbeitungsrechte noch Zugriff auf einzelne Fotos
oder Unterschriftsdateien. PDFs werden privat und ohne Cache ausgeliefert.

## Konsequenzen

Der Abschluss begrenzt Multipart-Anfragen vor CSRF- und Formularverarbeitung auf
2 MiB; ein vorgeschalteter Upload-Handler begrenzt einzelne Dateien auf 512 KiB
und alle Dateien zusammen auf 1 MiB. Zusätzlich zählt ein begrenzter Eingabestream
die tatsächlich gelesenen Bytes. Überschreitungen liefern HTTP 413, temporäre
Uploads werden geschlossen, und die Zeichnungen bleiben im geöffneten Formular.

Der Export verarbeitet höchstens 40 Fotos mit insgesamt 64 MiB einschließlich
aller Einzugsreferenzen. Jede Datei wird begrenzt gelesen (höchstens 8 MiB),
und Bilder über 16 Megapixel werden vor dem Dekodieren abgelehnt. Die gesamte
Bildsammlung im PDF darf nach der Aufbereitung höchstens 12 Megapixel und 24 MiB
belegen; damit sind auch stark komprimierbare Bilder im Arbeitsspeicher begrenzt.
Ein begrenzter Ausgabepuffer akzeptiert höchstens 32 MiB PDF-Daten. Diese Grenzen
gelten ebenso für historische Exporte. Sie verhindern unbeschränkte Arbeit im
synchronen Worker ohne neue Infrastruktur. Bei Überschreitung erfolgt kein
Abschluss und keine unvollständige Archivierung; Bilder werden niemals still
weggelassen. Bereits archivierte PDFs bleiben unverändert herunterladbar.

- Neue Abschlüsse benötigen JavaScript und eine erfolgreich gespeicherte PDF-Datei.
- Fehlende oder beschädigte Fotos verhindern einen unvollständigen Abschluss.
- Vor dem Abschluss bearbeitet die Maske vorhandene Prüfpunkte und Schlüssel über
  ihre zum Protokoll gehörenden IDs. Gespeicherte Fotos behalten ihre Zuordnung;
  ältere Entwürfe ohne Prüfpunkt-ID werden über Raum und Merkmal zugeordnet.
  Die Entwurfswiederherstellung ergänzt bestehende Formularfelder, statt sie neu
  aufzubauen. Dadurch bleiben gespeicherte Fotos und im geöffneten Formular
  ausgewählte Dateien erhalten. Nach einem Neuladen müssen ungespeicherte
  Dateien aus Sicherheitsgründen erneut ausgewählt werden.
- Stamm- und Referenzdatenänderungen verändern keine archivierten Dokumente.
- PDF-Layouts sind versionierte Ausgaben; bestehende PDFs werden nicht neu gestaltet.
- US-11 bleibt ein eigener Branch/PR auf Basis des Fotofeatures. Die additive
  Migration `0018_merge_photo_safety_and_pdf` verbindet dessen Sicherheitsmigration
  mit der PDF-Migration. Nach dem Merge des Fotofeatures ist der US-11-Branch auf
  den integrierten Stand zu setzen; der eigene PR enthält nur die US-11-Änderungen.
