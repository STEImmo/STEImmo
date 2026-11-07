# Zugriffsmatrix: PDF-Downloads und Exporterstellung (#140)

Teilprüfung von [Issue #140](https://github.com/STEImmo/STEImmo/issues/140)
auf `test/140-application-document-access`. Ergänzt die Nachweise für
[Bewerbungsdokumente](application-document-access.md) und [Fotos](photo-access.md).
Fachliche Grundlage ist
[ADR-0014](decisions/0014-pdf-export-und-touch-unterschriften.md).

## Endpunktinventar

Alle fünf Views liegen in `wohnungsverwaltung/export_views.py`; ihre Routen
sind in `wohnungsverwaltung/urls.py` unter `/uebergaben/` definiert.

| URL-Name (`wohnungsverwaltung:`) | Pfad nach dem Präfix | Methode | Berechtigung |
|---|---|---|---|
| `handover_protocol_mine` | `meine/` | GET | Mieterbereich; ausschließlich eigene unterschriebene Protokolle |
| `handover_protocol_pdf` | `<protocol_id>/pdf/` | GET | Mitarbeiter oder Mieterbereich mit Objektzuordnung; nur unterschrieben |
| `handover_protocol_pdf_create` | `<protocol_id>/pdf/erstellen/` | POST, CSRF | gleiche Objektgrenze; einmalige nachträgliche Archivierung eines Altprotokolls |
| `handover_protocol_finalize` | `<protocol_id>/abschluss/` | GET | Mitarbeiter; Abschlussvorschau für offene Protokolle |
| `handover_protocol_confirm` | `<protocol_id>/bestaetigen/` | POST, CSRF | Mitarbeiter; neuer Abschluss nur bei offenem Protokoll und gültigen Bestätigungsdaten |

PDF-Downloads und nachträgliche PDF-Erstellung erhalten nur eine Protokoll-UUID.
Es gibt keinen zusätzlichen frei wählbaren Datei-, Unterschrifts- oder Kindschlüssel.
Die Datei wird ausschließlich aus dem erlaubten Protokoll geladen. Der neue
Abschluss bindet die URL-UUID zusätzlich über den signierten Inhaltsfingerprint
an den geprüften Stand und das handelnde Mitarbeiterkonto.

## Rollen- und Objektmatrix

| Akteur | persönliche Liste | PDF-Download / nachträgliche Archivierung | Vorschau / neuer Abschluss |
|---|---|---|---|
| anonym oder während der Sitzung deaktiviert | 302 zur Anmeldung | 302 zur Anmeldung | 302 zur Anmeldung |
| Bewerber A/B oder nur Staff-Flag | 403 | 403 | 403 |
| Mieter mit eigener unterschriebener Übergabe | nur eigene unterschriebene Protokolle | erlaubt | 403 |
| Mieter mit fremder Übergabe, auch bei gleicher aktueller Wohnung | fremde Übergabe fehlt | 404 | 403 |
| Mitarbeiter ohne zusätzliches Mieterrecht | 403 | alle unterschriebenen Protokolle | erlaubt |
| direktes Mieterbereichsrecht | wie Mieterrolle | wie Mieterrolle | 403 |
| direktes Mitarbeiterbereichsrecht | wie Mitarbeiterrolle | wie Mitarbeiterrolle | erlaubt |
| Mieterrecht während bestehender Sitzung entzogen, ohne weiteren Berechtigungsweg | 403 | 403 | 403 |
| Mitarbeiter zum Mieter zurückgestuft | nur eigene unterschriebene Protokolle | nur eigene; fremde 404 | 403 |
| Mieterrecht vorhanden, Personenverknüpfung entfernt | leere Liste | 404 | 403 |

Die Objektzuordnung erfolgt über `Protokoll.person.user`. Der aktuelle
Wohnungsbezug gewährt keinen Zugriff auf Unterlagen früherer Bewohner.
Mitarbeiter sind nicht einzelnen Übergaben zugeordnet. Die fünf Endpunkte
verwenden dieselben Seitenrechte unabhängig davon, ob diese über eine Gruppe
oder direkt am Konto vergeben wurden.

| Zustand / Anfrage | Verhalten bei ausreichendem Seitenrecht |
|---|---|
| eigenes bzw. für Mitarbeiter beliebiges unterschriebenes Protokoll mit intaktem Archiv | PDF-Download 200, bytegenau das gesicherte Archiv |
| offenes oder gesperrtes Protokoll | kein PDF-Download und keine nachträgliche Archivierung, auch wenn bereits Archivbytes existieren: 404 |
| unterschriebenes Altprotokoll ohne Archiv und ohne Sicherungsmetadaten | einmalige nachträgliche Archivierung per POST; ausdrücklich als nachträglich gesichert markiert, keine erfundenen Unterschriften |
| bereits vorhandenes Archiv, erneuter Erstellungs-POST | Weiterleitung zum Download; keine neuen Bytes, Unterschriften oder geänderten Metadaten |
| fehlendes oder beschädigtes Archiv mit vorhandenem Pfad | Download 503; ein Erstellungs-POST erzeugt keine stille Ersatzdatei |
| Archivpfad fehlt, aber Snapshot, Sicherungszeit oder Unterschriften bestehen | Erstellungs-POST 503; keine Neuerzeugung als Altprotokoll |
| gültiger neuer Abschluss | Protokoll, Snapshot, PDF und Unterschriften werden gemeinsam gesichert |
| offenes Protokoll: Token eines anderen Protokolls, eines anderen Mitarbeiters, manipuliert oder fehlend | 409 vor Archivierung; keine Dateien, Unterschriften oder Statusänderung |
| Mitarbeiterrecht nach Vorschau entzogen | Bestätigungs-POST 403, auch mit zuvor gültigem Token |
| bereits unterschriebenes Protokoll erneut bestätigen | idempotente Antwort ohne neue Archivierung |
| gesperrtes Protokoll neu bestätigen | 404 |
| unbekannte Protokoll-UUID | 404, soweit die Rolle den betreffenden Endpunkt grundsätzlich verwenden darf |
| nicht erlaubte HTTP-Methode | 405 vor Archivzugriff, einschließlich HEAD bei GET-Endpunkten |

Listen und zulässige Exportantworten sind privat und ohne Cache.
Downloads verwenden außerdem `application/pdf`, Attachment mit Protokoll-ID und
`X-Content-Type-Options: nosniff`. Unterschriftsdateien haben keinen separaten
öffentlichen Download-Endpunkt.

## Bereits vorhandene Tests

Die folgenden Methoden liegen in `test_handover_export.HandoverExportTests`,
sofern kein anderer Testfall genannt ist.

| Prüfaspekt | Vorhandener Nachweis |
|---|---|
| eigene/fremde Mieter-PDFs, Wohnungswechsel und persönliche Liste | `test_tenant_only_sees_own_signed_protocols_even_after_moving` |
| Mieter dürfen keinen neuen Abschluss erstellen; Rollen-/Methoden-/Headerstichprobe | `test_permissions_http_methods_and_private_headers` |
| offene und gesperrte Protokolle sind nicht exportierbar | `test_open_and_blocked_protocols_cannot_be_exported` |
| einmalige nachträgliche Archivierung und Kennzeichnung | `test_legacy_protocol_is_explicitly_marked_and_created_once` |
| Unterschriften, Integrität und unveränderliches Archiv | `test_signatures_and_full_content_are_embedded_in_an_immutable_pdf`, `test_corrupt_archive_is_not_rebuilt` |
| veränderter Inhalt bzw. anderer Mitarbeiter macht Token ungültig | `test_changed_content_invalidates_signatures`, `test_token_is_bound_to_the_employee_and_protocol` — letzterer prüfte bisher tatsächlich nur den anderen Mitarbeiter |
| CSRF für Abschluss und Archivierung durch Mitarbeiter | `test_csrf_is_required_for_finalization_and_legacy_generation` |
| Upload-/Exportgrenzen, Pflichtdaten, Fehler und Rollback | weitere Tests in `HandoverExportTests` und `test_handover_archive_recovery.HandoverArchiveRecoveryTests` |
| parallele Bestätigungen und Serialisierung mit Bearbeitung | `test_handover_export.HandoverExportConcurrencyTests` |
| gesicherte Namen, Beschriftungen und Zuordnungen trotz späterer Stammdatenänderung | vorhandene Archivtests in `test_handover_archived_tenant.py`, `test_handover_archived_display.py` und `test_handover_archived_assignment.py` |

## Ergänzte echte Abdeckungslücken

`wohnungsverwaltung/test_pdf_access.py` ergänzt 19 Tests mit der vorhandenen
Export-Testvorbereitung. Alle Konten, Protokolle und Unterschriften sind fiktiv;
PDFs werden über den echten Abschluss- bzw. Altprotokollablauf in einem
temporären Medienverzeichnis erzeugt.

- Rollenmatrix über alle fünf Endpunkte, einschließlich beider Bewerber,
  reinem Staff-Flag, zweitem Mitarbeiter und direkter Rechtevergabe;
- zwei unterscheidbare unterschriebene Archive: exakte Bytes, richtige
  Download-ID und strikt getrennte persönliche Listen einschließlich
  Ausschluss eigener offener/gesperrter Protokolle;
- Altprotokoll-Erstellung durch den berechtigten Mieter, fremde aktuelle
  Wohnungszuordnung ohne Zugriff und idempotenter wiederholter POST;
- Rechteentzug, Rollenwechsel und Deaktivierung in bestehenden Sitzungen,
  insbesondere ein bereits gültiger Abschluss-Token nach Rechteentzug;
- Entzug der Personenverknüpfung ohne Änderung des bestehenden Archivs;
- offene/gesperrte Protokolle trotz vorhandener Archivbytes, unbekannte UUIDs
  und nicht erlaubte Methoden über alle Export-Endpunkte;
- fehlender, manipulierter und auf ein anderes Protokoll übertragener Token;
- CSRF mit vollständigen zulässigen Abschlussdaten sowie bei einer sonst
  zulässigen nachträglichen Archivierung durch den Mieter;
- fehlende Archivdatei ohne stille Wiederherstellung durch Mitarbeiter oder
  Mieter sowie direkte PDF-/Unterschrift-Medienpfade im Django-Routing.

Bei verweigerten Zugriffen müssen Storage-Lesen und -Schreiben ausbleiben.
Zusätzlich werden die tatsächlichen Mediendateien, Protokollfelder,
Unterschriften und Wohnungsstatus vor und nach dem Request verglichen.

Alle 19 neuen Tests bestehen bereits gegen den unveränderten Produktivcode.
Es ist kein Fehler nachgewiesen, der eine Änderung der Zugriffskontrolle
erfordert; der Teilpunkt ergänzt Tests und Prüfnachweise.

## Prüfstand und verbleibende Grenze

Die 19 neuen Tests bestehen separat gegen PostgreSQL. Auch die vollständige
Django-Suite (`python manage.py test --noinput`) besteht mit **964 Tests**,
einschließlich aller 19 neuen PDF-Tests; Laufzeit 631 Sekunden.
`manage.py check`, `makemigrations --check --dry-run`, `ruff check .`,
`ruff format --check .` und `git diff --check` sind erfolgreich. Der vollständige
Diff wurde geprüft. Es sind keine neuen Migrationen oder Abhängigkeiten nötig.
Der Teilpunkt PDF-Downloads und Exporterstellung ist damit im dokumentierten
Umfang abgeschlossen; in den isolierten Tests wurde kein objektübergreifender
Zugriff nachgewiesen.

Damit sind die drei Anwendungsbereiche von #140 inventarisiert. Der ergänzende
[Proxy-Prüfnachweis](private-media-proxy.md) belegt die Sperre tatsächlich
vorhandener künstlicher Dateien über einen laufenden Caddy auf localhost.
Er grenzt die lokale Prüfung von einer späteren Abnahme der Zielinstallation ab.
Vor produktivem Betrieb sind dort dieselbe Medienregel und Mount-Trennung zu
bestätigen. Anschließend sind alle Teilnachweise gemeinsam gegen die
Akzeptanzkriterien zu prüfen sowie Review und Merge abzuschließen. Push und
externe PR-/Issue-Aktionen gehören nicht zu diesem Auftrag.
