# Zugriffsmatrix: Bewerbungsdokumente (#140)

## Umfang und Grundlage

Teilprüfung von [Issue #140](https://github.com/STEImmo/STEImmo/issues/140),
begonnen am 04.11.2026 auf `main` bei `09b3b34`.
Die fachlichen Regeln stehen in
[ADR-0008](decisions/0008-rollen-und-zugriffskontrolle.md).
Dies ist ein Test- und Abdeckungsnachweis, keine neue Berechtigungsentscheidung.
Fotos, Übergabe-PDFs und die Prüfung am tatsächlichen Reverse Proxy gehören
weiterhin zum übergeordneten Issue und sind hier nicht abgenommen.

## Endpunktinventar

Alle vier Views liegen in `wohnungsverwaltung/views.py`; die Routen stehen in
`wohnungsverwaltung/urls.py` unter dem Präfix `/uebergaben/`.
Downloads unterstützen ausschließlich GET.

| URL-Name (`wohnungsverwaltung:`) | Pfad nach dem Präfix | Datenquelle |
|---|---|---|
| `applicant_application_document` | `bewerbung/<application_id>/nachweise/<document_type>/` | älteres Dateifeld der Bewerbung |
| `applicant_application_proof_download` | `bewerbung/<application_id>/nachweise/datei/<proof_id>/` | `ApplicationProof` |
| `employee_application_document` | `bewerbungen/mitarbeiter/<application_id>/nachweise/<document_type>/` | älteres Dateifeld der Bewerbung |
| `employee_application_proof_download` | `bewerbungen/mitarbeiter/<application_id>/nachweise/datei/<proof_id>/` | `ApplicationProof` |

Erlaubte ältere Dokumentfelder: `income_proof`, `identity_proof`,
`credit_report_proof`. Die entsprechenden aktuellen Kategorien sind `income`,
`identity`, `credit_report`. Beliebige andere Modellfelder dürfen nicht
über `document_type` ausgewählt werden.

## Rollen- und Objektmatrix

Die Angaben gelten für vorhandene, lesbare Dateien. Bei den Bewerber-Endpunkten
muss eine Person mit dem Konto verknüpft sein.

| Akteur / Zustand | Bewerber-Endpunkte | Mitarbeiter-Endpunkte |
|---|---|---|
| anonym | 302 zur Anmeldung | 302 zur Anmeldung |
| deaktiviertes Konto, zuvor angemeldet | 302 zur Anmeldung | 302 zur Anmeldung |
| ausschließlich Mieterrolle | 403 | 403 |
| Bewerber, eigene offene und freigeschaltete Bewerbung | 200 | 403 |
| Bewerber, fremde Bewerbung | 404 | 403 |
| Mieter mit erhaltener Bewerberrolle | wie Bewerber, ausschließlich eigene Dokumente | 403 |
| ausschließlich Mitarbeiterrolle | 403 | 200 bei eingereichter Bewerbung |
| Seitenrecht direkt am Konto | gleiche fachliche Regeln wie über die Gruppe | gleiche fachliche Regeln wie über die Gruppe |
| benötigte Rolle bzw. direktes Seitenrecht während der Sitzung entzogen | 403, sofern kein weiterer Berechtigungsweg besteht | 403, sofern kein weiterer Berechtigungsweg besteht |
| Bewerberrecht ohne verknüpfte Person | 403 | ohne Mitarbeiterrecht 403 |

| Bewerbung / URL-Kombination | berechtigter Bewerber | berechtigter Mitarbeiter |
|---|---|---|
| freigeschalteter eigener Main-Entwurf | 200 | 404 |
| eingereicht, offen, nicht zurückgezogen, freigeschaltet | 200 | 200 |
| Main-Freigabe fehlt | 404 | 200, falls bereits eingereicht |
| zurückgezogen, abgelehnt oder gesperrt | 404 | 200, falls bereits eingereicht |
| eigene Bewerbungs-ID mit fremder Datei-ID | 404 | 404 bei nicht zusammengehörenden IDs |
| unbekannte Bewerbungs- oder Datei-ID | 404 | 404 |

Mitarbeiter sind nicht einzelnen Bewerbungen zugeordnet. Ihr Zugriff auf
eingereichte Dokumente bleibt nach Rücknahme, Ablehnung oder Sperre bewusst
erhalten. Eine Mieterrolle allein gewährt keinen Zugriff auf Bewerbungsunterlagen.

Erfolgreiche Downloads liefern die Datei als Attachment mit
`Content-Type: application/octet-stream`, `X-Content-Type-Options: nosniff`
und `Cache-Control: private, no-store`.

## Bereits vorhandene Tests

| Prüfaspekt | Vorhandener Nachweis |
|---|---|
| eigener aktueller Entwurf; Freigabe; Rücknahme; fremder Bewerber | `tests.MainApplicationUploadTests`: `test_applicant_can_download_their_own_saved_proof`, `test_locked_application_cannot_be_edited_or_have_documents_downloaded`, `test_applicant_cannot_download_proofs_after_withdrawal`, `test_applicant_cannot_access_another_applicants_form_or_files` |
| Mitarbeiter dürfen aktuelle Entwürfe nicht laden | `tests.MainApplicationUploadTests.test_employee_sees_pre_data_but_cannot_view_or_download_main_draft` |
| ältere Entwürfe und gemischte Bewerbungs-/Datei-IDs auf Mitarbeiterseite | `test_employee_dashboard.EmployeeDashboardDisclosureTests`: `test_employee_cannot_bypass_draft_protection_with_direct_or_mixed_urls`, `test_employee_cannot_mix_two_submitted_application_and_proof_ids` |
| eingereichte aktuelle Dateien in allen Bewertungszuständen | `test_employee_dashboard.EmployeeDashboardDisclosureTests.test_employee_downloads_submitted_files_in_all_review_statuses` |
| Rollenentzug und deaktivierter Mitarbeiter bei aktuellem Download | `test_employee_dashboard.EmployeeDashboardDisclosureTests.test_revoked_employee_permission_and_disabled_accounts_lose_access` |
| Mitarbeiterrolle ist kein Bewerberrecht; Staff-Flag genügt nicht | `test_employee_dashboard.EmployeeDashboardDisclosureTests`: `test_employee_role_does_not_grant_applicant_or_user_management_access`, `test_staff_flag_alone_does_not_grant_dashboard_or_download_access` |
| erlaubte ältere Feldnamen auf Mitarbeiterseite | `test_employee_dashboard.EmployeeDashboardDisclosureTests.test_legacy_document_type_cannot_select_arbitrary_model_fields` |
| Downloadheader, Dateiformat, fehlende Datei und gleichzeitiges Löschen | `tests.MainApplicationUploadTests`: Tests ab `test_accepted_pdf_with_trailing_whitespace_can_be_downloaded` bis `test_missing_stored_proof_returns_not_found` |
| direkter Medienpfad in Django nicht erreichbar | `test_employee_dashboard.EmployeeDashboardDisclosureTests.test_uploaded_files_have_no_direct_media_url_even_for_employees` — kein Nachweis für den Reverse Proxy |

## Ergänzte Lücken

`wohnungsverwaltung/test_application_document_access.py` ergänzt die Matrix:

- anonyme Nutzer und reine Mieter für alle vier Downloadwege und drei Kategorien;
- fremde Bewerber auch am älteren Bewerber-Download;
- positive Downloads aller drei älteren und aktuellen Kategorien;
- Mieter mit zusätzlicher Bewerberrolle und weiterhin wirksamer Eigentumsprüfung;
- gemischte Bewerbungs-/Datei-IDs am Bewerber-Endpunkt in beiden Richtungen;
- ältere eigene Entwürfe und deren Sperre für Mitarbeiter;
- Ablehnung, Sperre, Rücknahme und fehlende Freigabe für beide Bewerber-Dateiformen;
- ältere Mitarbeiterdownloads nach Ablehnung, Sperre oder Rücknahme;
- Deaktivierung, Gruppenentzug und Entzug direkt vergebener Rechte nach einem
  erfolgreichen Download in derselben Sitzung, jeweils für beide Dateiformen;
- fehlende Personenverknüpfung, unbekannte UUIDs und unzulässige ältere Feldnamen.

Verweigerte Zugriffe werden zusätzlich darauf geprüft, dass keine private Datei
geöffnet wird. Testdateien liegen in einem temporären Medienverzeichnis;
Konten und Dokumente sind ausschließlich fiktiv. Jede Person, Kategorie und
Dateiform erhält einen unterscheidbaren PDF-Inhalt; erfolgreiche Downloads
müssen bytegenau die angeforderte Datei liefern.

Neue Tests auf bereits bestehende Schutzmechanismen können unmittelbar grün sein.
Produktivcode wird nur geändert, falls ein Test einen tatsächlichen Fehler belegt.

## Ausführung und verbleibende Grenzen

Prüfstand am 05.11.2026: Das Inventar und die Zuordnung bestehender Tests sind
abgeschlossen. Die 14 ergänzten Tests bestehen in der regulären
PostgreSQL-Testdatenbank mit unveränderten Migrationen. Verwendet wurden
Python 3.13.16, Django 5.2.17 und der lokale PostgreSQL-18.6-Container.
Der zuvor blockierende lokale Docker-/WSL-Startfehler ist behoben; die frühere
SQLite-Ersatzprüfung ist damit nicht mehr die Grundlage der Abnahme.

`manage.py check`, `makemigrations --check --dry-run`, `ruff check .` und
`ruff format --check .` sind erfolgreich. Es sind keine neuen Migrationen oder
Änderungen am Produktivcode erforderlich. Die vollständige Django-Testsuite
(`python manage.py test --noinput`) besteht mit **929 Tests**, einschließlich
der 14 ergänzten Zugriffstests. Laufzeit: 501 Sekunden. Der vollständige Diff
und `git diff --check` wurden ebenfalls geprüft.

Im ersten PostgreSQL-Lauf schloss ein neuer Testhelfer bereits geschlossene
HTTP-Antworten erneut. Das beendete die Testdatenbankverbindung; der Helfer
schließt Antworten jetzt nur, wenn sie noch offen sind. Nach dieser Korrektur
bestehen sowohl die 14 neuen Tests separat als auch die vollständige Suite.

Damit ist der Teilpunkt Bewerbungsdokumente im hier dokumentierten Umfang
abgenommen. In diesen isolierten Zugriffstests wurde kein objektübergreifendes
Datenleck nachgewiesen. Daraus folgt keine vollständige Sicherheitsabnahme des
Deployments oder des übergeordneten Issues.

Gezielte Prüfung der neuen Tests und ihrer bestehenden fachlichen Nachbartests:

```text
python manage.py test wohnungsverwaltung.test_application_document_access wohnungsverwaltung.tests.MainApplicationUploadTests wohnungsverwaltung.test_employee_dashboard --noinput
```

Die ergänzenden Matrizen stehen im [Foto-Prüfnachweis](photo-access.md) und im
[PDF-/Exporterstellungs-Prüfnachweis](pdf-access.md). Der zusätzliche
[lokale Proxy-Prüfnachweis](private-media-proxy.md) bestätigt die Sperre
tatsächlich vorhandener künstlicher Dateien über Caddy auf localhost.
Vor produktivem Betrieb sind dieselbe Medienregel und Mount-Trennung auf
der Zielinstallation zu bestätigen. Echte Personenunterlagen und produktive
Angriffstests sind kein Bestandteil dieser Prüfung.
