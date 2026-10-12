# ADR-0011: Foto-Dubletten und Rückkehr aus der Protokollübersicht

## Kontext

Prüfpunktfotos können sowohl beim Anlegen eines Protokolls als auch später in
der Protokollübersicht gespeichert werden. Ohne Inhaltsprüfung konnten gleiche
Bilddateien mehrfach an demselben Prüfpunkt gespeichert werden. Außerdem
verließ ein Upload aus der Übersicht unerwartet die Übersicht und öffnete die
Raum-Unterseite.

## Entscheidung

Für jedes neue Foto wird ein SHA-256-Hash des geprüften Dateiinhalts gespeichert.
Pro Prüfpunkt ist dieser Hash eindeutig. Bereits vorhandene ältere Fotos ohne
Hash werden beim nächsten Upload dennoch anhand ihres Dateiinhalts berücksichtigt;
sie werden nicht nachträglich verändert oder gelöscht.

Ist die Datei eines älteren Fotos für den Abgleich nicht lesbar, wird der neue
Upload mit einer verständlichen Fehlermeldung abgelehnt (Issue #68). Es werden
keine neuen Dateien gespeichert und keine Bestandsfotos entfernt. Der Abgleich
kann nach Wiederherstellung des Speicherzugriffs erneut erfolgen. Bereits
gespeicherte Inhalts-Hashes benötigen keinen erneuten Zugriff auf die Originaldatei.

Auch das Protokoll-Bearbeitungsformular gleicht ältere Fotos anhand ihres Inhalts
ab (Issue #69). Nach der endgültigen Raumzuordnung werden die Inhalts-Hashes des
tatsächlich betroffenen Prüfpunkts vor Schreibvorgängen ermittelt. Nicht lesbare
Bestandsfotos erzeugen einen Foto-Feldfehler. Identischer Inhalt wird bei der
Speicherung übersprungen; ältere Fotos ohne gespeicherten Hash bleiben unverändert.
Ohne neue Fotoauswahl ist für normale Protokolländerungen kein Dateiabgleich nötig.

Die Fotoanzahl wird auf beiden Uploadwegen erst nach dem Abgleich geprüft
(Issue #70). Bereits gespeicherter Inhalt wird aus der neuen Fotoauswahl entfernt.
Zur Grenze zählt die Anzahl der bestehenden Fotoeinträge plus tatsächlich neue
Fotos; die konfigurierte Grenze wird nicht erhöht. Ein wiederholter Upload bei
voller Kapazität erzeugt deshalb keinen Limitfehler. Bei einer tatsächlichen
Überschreitung werden weiterhin weder Fotos noch Protokolländerungen gespeichert.

Beim Entfernen und Ersetzen eines einzelnen Prüfpunkts berücksichtigt der Abgleich
nur fortbestehende Gegenstücke (Issue #86). Das Formset ermittelt zuerst die zur
Löschung markierten, bereits auf dieses Protokoll begrenzten Prüfpunkt-IDs.
Diese Einträge zählen weder zur Dublettenprüfung noch zur Fotoanzahl des Ersatzes.
Eine gleichzeitig ausdrücklich über dieselbe ID übermittelte Änderung erzeugt
einen Feldfehler. Die Speicherung entfernt markierte Prüfpunkte vor neuen oder
geänderten Zeilen, unabhängig von deren Formularreihenfolge. Alle Schritte und
Bereinigungsaufträge bleiben in der bestehenden Protokolltransaktion; alte
Dateien werden erst nach deren erfolgreichem Commit gelöscht.

Ein Upload oder das Entfernen eines Fotos aus der Protokollübersicht führt mit
einem Fragment direkt zum betroffenen Prüfpunkt dieser Übersicht zurück. Die
Raum-Unterseite bleibt nur das Ziel für die dort gestarteten Aktionen.

## Konsequenzen

- Das gleiche Bild kann nicht versehentlich mehrfach am selben Prüfpunkt
  gespeichert werden.
- Bestehende Bilddateien und ihre Beweiskette bleiben unverändert.
- Die Bedienung der Übersicht bleibt nach Fotoaktionen im gewählten Kontext.
