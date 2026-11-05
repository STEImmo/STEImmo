# Zugriffsmatrix: Fotos (#140)

Teilprüfung von [Issue #140](https://github.com/STEImmo/STEImmo/issues/140),
auf demselben Branch wie die bereits geprüften
[Bewerbungsdokumente](application-document-access.md).
Grundlage sind [ADR-0013](decisions/0013-foto-sicherheit-und-eindeutige-pruefpunkte.md)
und die bestehende Rollenverteilung aus
[ADR-0008](decisions/0008-rollen-und-zugriffskontrolle.md).

## Endpunkte

| URL-Name | Methode | Schutz und Objektbindung |
|---|---|---|
| `wohnungsverwaltung_public:apartment_photo` | GET | Foto-UUID; ohne Mitarbeiterrecht nur Fotos freier Wohnungen |
| `verwaltung:apartment_photos` | GET, POST | Mitarbeiterrecht; Wohnung muss existieren; POST mit CSRF |
| `verwaltung:apartment_photo_delete` | POST | Mitarbeiterrecht und CSRF; Foto muss zur Wohnungs-ID gehören |
| `wohnungsverwaltung:handover_protocol_checklist_item_photo_view` | GET | Mitarbeiterrecht; zusammengehörige Protokoll-, Raum-, Prüfpunkt- und Foto-ID |
| `wohnungsverwaltung:handover_protocol_checklist_item_photo_upload` | POST | Mitarbeiterrecht und CSRF; zusammengehörige Protokoll-, Raum- und Prüfpunkt-ID; Protokoll offen |
| `wohnungsverwaltung:handover_protocol_checklist_item_photo_delete` | POST | Mitarbeiterrecht und CSRF; zusammengehörige Protokoll-, Raum-, Prüfpunkt- und Foto-ID; Protokoll offen |

Die Routen sind in `public_urls.py`, `verwaltung_urls.py` und `urls.py` der
App `wohnungsverwaltung` definiert; die Views liegen in `views.py`.
Fotos können zusätzlich über die bestehenden Protokollformulare gespeichert
oder beim Entfernen eines Prüfpunkts/Raums gelöscht werden. Diese Wege bleiben
durch die Mitarbeiterberechtigung und dieselbe Protokoll-Schreibsperre geschützt;
ihre vorhandenen Fachtests werden weiterhin mit ausgeführt.

## Rollen- und Objektmatrix

| Akteur | Foto einer freien Wohnung | Foto belegter/gesperrter Wohnung | Wohnungsfotopflege | Übergabefotos anzeigen / ändern |
|---|---|---|---|---|
| anonym | 200 | 404 | 302 zur Anmeldung | 302 zur Anmeldung |
| Bewerber A oder B | 200 | 404 | 403 | 403 |
| nur Mieterrolle, auch eigene Übergabe | 200 | 404 | 403 | 403 |
| nur `is_staff`, ohne Seitenrecht | 200 | 404 | 403 | 403 |
| aktiver Mitarbeiter, auch ohne `is_staff` | 200 | 200 | erlaubt | erlaubt, Änderungen nur bei offenem Protokoll |
| direktes `access_employee_area`-Recht | wie Mitarbeiter | wie Mitarbeiter | erlaubt | wie Mitarbeiter |
| während der Sitzung zum Mieter zurückgestuft bzw. direktes Recht entzogen | 200 | 404 | 403 | 403 |
| während der Sitzung deaktiviert | 200 | 404 | 302 zur Anmeldung | 302 zur Anmeldung |

Wohnungsfotos einer freien Wohnung sind bewusst öffentliches Bildmaterial.
Wird der Wohnungsstatus geändert, ist derselbe Foto-Link ohne Mitarbeiterrecht
nicht mehr abrufbar. Übergabefotos sind dagegen unabhängig von Personenzuordnung
oder Wohnungsstatus privat. Mieter erhalten eigene unterschriebene PDFs über die
separaten PDF-Endpunkte; die Mieterrolle erlaubt keinen einzelnen Rohfotoabruf.

Mitarbeiter dürfen gespeicherte Übergabefotos offener, unterschriebener und
gesperrter Protokolle lesen. Offene Protokolle sind gespeicherte Arbeitsstände,
keine öffentliche Veröffentlichung. Unterschriebene und gesperrte Protokolle
erlauben keine Fotoänderung. Ein nicht gespeicherter Browser-Entwurf erhält
hierdurch keinen separaten Foto-Endpunkt.

Unbekannte UUIDs und nicht zusammengehörende Eltern-/Kind-IDs ergeben 404.
Nicht erlaubte Methoden ergeben bei berechtigten Nutzern 405; insbesondere
wird auch HEAD entsprechend dem bestehenden Wohnungsfoto-Endpunkt abgewiesen.

Alle erfolgreichen Fotoabrufe liefern einen festen, geprüften Bildtyp,
`X-Content-Type-Options: nosniff` und `Cache-Control` mit `private, no-store`.
Die Header weisen Browser und Proxys an, die Antwort nicht zu speichern;
sie garantieren keine nachträgliche Löschung bereits kopierter Bilddateien.

## Vorhandene Abdeckung vor dieser Ergänzung

| Prüfaspekt | Bestehende Tests |
|---|---|
| öffentlicher Abruf eines hochgeladenen Wohnungsfotos | `test_building_view.ApartmentPhotoTests.test_employee_can_upload_and_public_gallery_displays_photo` |
| belegte Wohnung für anonyme Nutzer verborgen | `ApartmentPhotoTests.test_photo_of_unavailable_apartment_is_hidden_from_public` |
| Wohnungsfoto-Upload/-Löschung nur für Mitarbeiter und mit CSRF | `ApartmentPhotoTests`: `test_anonymous_and_non_employee_cannot_upload`, `test_upload_requires_csrf`, `test_delete_requires_employee_permission_and_csrf` |
| Wohnungsfoto nicht über fremde Wohnungs-ID löschbar | `ApartmentPhotoTests.test_other_apartment_photo_cannot_be_deleted_through_wrong_apartment` |
| Upload, Mitarbeiter ohne Staff-Flag, anonymer Übergabefotoabruf | `tests.HandoverProtocolViewsTests.test_employee_can_attach_multiple_photos_to_an_existing_checklist_item` |
| tatsächlicher Bildtyp statt Browser-MIME-Angabe | `HandoverProtocolViewsTests`: `test_photo_view_uses_a_verified_mime_type`, `test_photo_upload_stores_the_verified_mime_type` |
| unterschriebene Übergabe unveränderbar | `HandoverProtocolViewsTests.test_confirmed_protocol_rejects_photo_changes` |
| Referenzbilder und archivierte Bildbeschriftung | `HandoverProtocolViewsTests.test_move_out_shows_matching_photos_from_the_latest_signed_move_in`; `test_handover_archived_display.HandoverArchivedDisplayTests.test_archived_photo_keeps_its_caption_and_can_still_be_enlarged` |
| Uploadvalidierung, Limits, Dubletten, Rollback und Dateibereinigung | bestehende Foto-Fachtests in `tests.py`, `test_photo_duplicates.py`, `test_photo_recovery.py`, `test_photo_deletion.py`, `test_apartment_photo_recovery.py` und Tests zum Austausch/Entfernen von Prüfpunkten und Räumen |

## Ergänzte Lücken und Korrektur

`wohnungsverwaltung/test_photo_access.py` ergänzt die fehlenden Rollen- und
Objektkombinationen. Die Tests verwenden ausschließlich fiktive Konten und
kleine, lokal erzeugte Bilder in einem temporären Medienverzeichnis:

- öffentliche Rollen, gesperrte Wohnungen, Mitarbeiterzugriff und sofortiger
  Sichtbarkeitswechsel nach Änderung des Wohnungsstatus;
- alle sechs Mitarbeiteraktionen: Pflegeseite, Wohnungsfoto-Upload/-Löschung,
  Übergabefotoabruf/-Upload/-Löschung;
- eigene Übergabefotos bei reiner Mieterrolle, Staff-Flag ohne Seitenrecht,
  Rollenwechsel, direkt vergebene Rechte und deren Entzug sowie Deaktivierung
  während einer bestehenden Sitzung;
- vollständige Kombination zweier Protokoll-/Raum-/Prüfpunkt-/Fotoketten:
  14 falsche Kombinationen für Abruf/Löschung und sechs für Upload;
- unbekannte UUIDs auf jeder Ebene, CSRF für die Übergabefoto-Schreibwege,
  GET auf Mutations-Endpunkten und Änderungen gesperrter Protokolle;
- bytegenaues Ergebnis für unterscheidbare Bilder, Cache-Schutz, Methodenbegrenzung
  sowie direkte Medienpfade im Django-Routing.

Verweigerte Abrufe dürfen keine Bilddatei öffnen. Bei verweigerten Aktionen
werden außerdem Datenbankeinträge und tatsächliche Mediendateien vor und nach
dem Request verglichen.

Der erste Testlauf gegen den unveränderten Produktivcode bestätigte zwei
Abruflücken bei Übergabefotos: fehlende Cache-Sperre und Bildauslieferung bei
anderen HTTP-Methoden als GET. Die View erhielt deshalb die vorhandene
Django-Absicherung `never_cache` und eine GET-Prüfung vor jedem Dateizugriff.
Die Rollen- und Objektprüfungen waren bereits vorhanden und bleiben erhalten.
Ein objektübergreifender Zugriff wurde in diesen Tests nicht nachgewiesen.

## Prüfstand und verbleibende Schritte

Prüfstand: 05.11.2026. Die gezielte Suite mit 99 neuen und vorhandenen Foto-/
Übergabe-/Archivtests besteht nach der Korrektur. Die 16 neuen Tests bestehen
auch nach Ergänzung der positiven Prüfung aller direkt vergebenen Fotorechte.
Django-Systemcheck, Migrationsprüfung und beide Ruff-Prüfungen sind erfolgreich.
Die vollständige Django-Testsuite (`python manage.py test --noinput`) besteht
gegen PostgreSQL mit **945 Tests**, einschließlich aller 16 neuen Fototests;
Laufzeit 486 Sekunden. Der vollständige Diff und `git diff --check` sind geprüft.
Es sind keine neuen Migrationen oder Abhängigkeiten erforderlich. Der
Teilpunkt Fotozugriffe ist damit im dokumentierten Umfang abgeschlossen.

Für den vollständigen Abschluss von #140 fehlen danach:

1. PDF-Downloads und Exporterstellung: Endpunktinventar, vorhandene Assertions
   zuordnen und Lücken der Rollen-/Objektmatrix einschließlich Sitzungswiderruf
   schließen. Vorhandene Exporttests ersetzen diese Zuordnung nicht.
2. Am tatsächlichen Reverse Proxy mit eigens erzeugten Testdateien prüfen,
   dass private Bewerbungsunterlagen, Fotos, PDF-Archive und Signaturdateien
   nicht direkt über Medienpfade ausgeliefert werden. Ein Django-404 beweist
   diese Servereigenschaft nicht. Keine produktiven Angriffstests oder Echtdaten.
3. Die Teilnachweise gemeinsam gegen alle Akzeptanzkriterien prüfen und den
   Branch anschließend reviewen und mergen. Push, PR-/Issue-Aktionen und Merge
   werden hier nicht ausgeführt.
