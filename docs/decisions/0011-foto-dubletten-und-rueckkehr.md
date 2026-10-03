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

Ein Upload oder das Entfernen eines Fotos aus der Protokollübersicht führt mit
einem Fragment direkt zum betroffenen Prüfpunkt dieser Übersicht zurück. Die
Raum-Unterseite bleibt nur das Ziel für die dort gestarteten Aktionen.

## Konsequenzen

- Das gleiche Bild kann nicht versehentlich mehrfach am selben Prüfpunkt
  gespeichert werden.
- Bestehende Bilddateien und ihre Beweiskette bleiben unverändert.
- Die Bedienung der Übersicht bleibt nach Fotoaktionen im gewählten Kontext.
