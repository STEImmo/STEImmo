# ADR-0008: Rollen und Zugriffskontrolle

## Kontext

STEImmo benötigt geschützte Bewerbungsdaten, einen Mitarbeiterbereich für Stammdaten und Übergaben sowie eine kontrollierte Pflege von Konten und Seitenrechten. Jede Person kann ohne Konto bestehen; jedes über die Anwendung angelegte Konto ist jedoch genau einer Person zugeordnet.

## Entscheidung

Django `User`, `Group` und `Permission` bilden die technische Grundlage. Die fachlichen Codenames und Decorators liegen zentral in `wohnungsverwaltung.access`; Views verwenden ausschließlich diese Decorators. Navigationslinks werden anhand derselben Berechtigungen angezeigt, ersetzen aber nie den serverseitigen Schutz.

| Zugriff | Django-Gruppe | Berechtigung | Aktuelle Seiten |
|---|---|---|---|
| Öffentlich | keine | keine | Startseite, Gesundheitscheck, Bewerbungsvorschau, Anmeldung, Registrierung und Code-Bestätigung |
| Bewerber | `Bewerber` | `access_applicant_area` | eigene Bewerbungen erstellen, Status einsehen und freigeschaltete Bewerbungen zurückziehen |
| Mieter | `Mieter` | `access_tenant_area` | eigene bestätigte Übergabeprotokolle und deren PDF-Export |
| Mitarbeiter | `Mitarbeiter` | `access_employee_area` | Verwaltung, Betreiber-Bewerbungsübersicht und alle Übergabeprotokoll-Endpunkte |
| Benutzerverwaltung | `Benutzerverwaltung` | `access_employee_area`, `manage_user_accounts` | zusätzlich Konto-, Rollen- und Rechteverwaltung |

Gruppen definieren die Standardrollen. Die vier Seitenrechte können zusätzlich direkt einem einzelnen Konto zugeordnet werden. Beim Übergang vom Bewerber zum Mieter bleibt die Bewerbergruppe bestehen; die Mietergruppe wird ergänzt.

Die Bewerbungsübersicht im Bewerberbereich lädt ausschließlich Bewerbungen der mit dem angemeldeten Konto verknüpften Person. Die Betreiberübersicht zeigt Mitarbeitern die Bewerbungen aller Wohnungen. Pre-Daten sind sichtbar; Main-Nachweise werden ausschließlich nach Einreichung über geschützte Downloads zugänglich. Nicht eingereichte Main-Entwürfe bleiben auch bei direkter URL-Eingabe verborgen. Eingereichte Nachweise bleiben für Mitarbeiter nach Rücknahme, Ablehnung oder Sperre zugänglich. Es gibt keine Zuordnung von Bewerbungen zu einzelnen Mitarbeitern. Ein Bewerber kann den Main-Bereich nur für eine eigene, offene und nicht zurückgezogene Bewerbung mit gesetztem `main_application_unlocked`-Status öffnen. Dieser Status gilt pro Bewerbung; der Mitarbeiterworkflow soll ihn nach Besichtigung und positiver Eignungsentscheidung setzen. Das Zurückziehen speichert einen endgültigen Zeitstempel an der Bewerbung.

Die Rollen und Permissions werden über Migration und idempotent nach `post_migrate` angelegt. Damit stehen sie auch nach einem Django-Testdatenbank-Flush zuverlässig bereit. Bestehende, mit einer Person verknüpfte Konten erhalten bei der Migration abhängig von `Person.is_employee` die Gruppe `Bewerber` oder `Mitarbeiter`.

Die UIkit-Benutzerverwaltung ist der einzige Pflegeweg für User und Gruppen in der Anwendung. Sie kann eine vorhandene konto-lose Person zuordnen oder eine neue Person samt Konto erstellen. Konten werden nur deaktiviert, nicht gelöscht. Der Django-Admin registriert `User` und `Group` nicht, damit keine parallele Kontoanlage ohne Personenbezug entsteht.

Bei der Selbstregistrierung werden `User` und `Person` atomar, aber zunächst mit `is_active=False` angelegt. Ein zufälliger sechsstelliger Bestätigungscode wird ausschließlich als Passwort-Hash gespeichert, gilt 15 Minuten und hat höchstens fünf Eingabeversuche. Nach erfolgreicher Bestätigung wird das Konto aktiviert und angemeldet. Ein erneuter Versand ersetzt den vorherigen Code; zwischen zwei Sendungen gilt eine Sperrzeit von einer Minute. In der Entwicklung stellt der ausschließlich im Compose-Override enthaltene Mailpit-Container ein lokales Testpostfach auf `localhost:8025` bereit. Er ist auf 100 temporäre E-Mails begrenzt und wird nicht in Produktion gestartet. Produktion verwendet einen konfigurierten SMTP-Backend. Ein Browser-Hinweis in der Anwendung enthält den Code bewusst nicht, weil er keinen vom Registrierungsbrowser getrennten Nachweis liefern würde.

Der Development-Override startet zusätzlich einen explizit fiktiven Mitarbeiter über `create_development_employee`. Die Compose-Variablen sind auf `mitarbeiter@example.test` und ein dokumentiertes lokales Passwort festgelegt. Der Command darf ausschließlich mit `DEBUG=True` laufen, erstellt die verknüpfte Person, aktiviert das Konto und vergibt die Gruppe `Mitarbeiter`. Bei jedem Entwicklungsstart stellt er diesen Zustand wieder her. Eine Datenmigration oder die Produktions-Compose-Konfiguration erzeugt kein solches Konto.

Jede Anmeldung eines Kontos mit `access_employee_area` oder `manage_user_accounts` erfordert Passwort und einen zusätzlichen E-Mail-Einmalcode. Das gilt auch für direkt zugewiesene Einzelrechte. Der Code wird ausschließlich als Passwort-Hash gespeichert, ist 15 Minuten gültig und hat höchstens fünf Versuche. Erst nach korrekter Eingabe legt die Anwendung die authentifizierte Session an; es gibt keine dauerhafte Gerätefreigabe. Eine neue Passwortanmeldung erstellt stets einen neuen Code. Änderungen an Rollen oder direkten Seitenrechten beenden die aktiven Datenbanksitzungen des betroffenen Kontos innerhalb derselben Transaktion. Damit kann eine vorherige Bewerberanmeldung die Mitarbeiter-MFA nicht umgehen. Erhält ein Konto bereits vor Abschluss der Selbstregistrierung solche Rechte, bestätigt ein weiterhin gültiger Registrierungscode nur das Konto; die automatische Anmeldung entfällt. Der Mitarbeiter muss anschließend die reguläre Passwort- und MFA-Anmeldung durchlaufen.

Die reguläre Anmeldung unter `/accounts/login/` begrenzt Passwortversuche für alle Kontoarten: Drei aufeinanderfolgende falsche Passwörter sperren das betroffene Konto für 15 Minuten. Zusätzlich begrenzen zehn Fehlversuche aus derselben IP-Adresse innerhalb von 15 Minuten weitere Anmeldungen dieser Quelle. Der Kontostatus und ein ausschließlich mit `SECRET_KEY` abgeleiteter IP-Fingerprint liegen transaktionssicher in PostgreSQL; Roh-IP-Adressen und Anmeldeprotokolle werden nicht gespeichert. Erfolgreiche Passwortanmeldungen löschen den Kontofehlerstatus, während die IP-Grenze als rollierendes Fehlversuchsfenster weiterläuft. Abgelaufene Zustände werden beim nächsten Anmeldeversuch gelöscht. Sperren verlängern sich durch weitere Anfragen nicht. Alle Fehlfälle liefern dieselbe neutrale Meldung. Standardmäßig wird `REMOTE_ADDR` verwendet; `X-Forwarded-For` gilt nur, wenn `REMOTE_ADDR` in `DJANGO_LOGIN_THROTTLE_TRUSTED_PROXY_IPS` konfiguriert ist. Django-Admin bleibt außerhalb des Geltungsbereichs.

Bei Passwortänderungen, geänderter Konto-E-Mail, geänderten Rollen oder Seitenrechten und
administrativer Deaktivierung verwirft die Benutzerverwaltung zusätzlich ausstehende
Registrierungs- und Mitarbeitercodes. Betroffene aktive Sitzungen werden beendet.
Ein bereits versendeter Code kann dadurch weder einen Passwortreset umgehen noch ein
administrativ deaktiviertes Konto reaktivieren. Beim Zuordnen eines bestehenden
Kontos zu einer anderen Person ist ein vom bisherigen Passwort abweichendes neues
Passwort erforderlich; die bisherigen Zugangsdaten dürfen nicht auf die neue Person
übergehen.

### Parallele Anmeldung und Kontowiderruf (Issue #63)

Der Abschluss einer Passwortanmeldung, die Ausstellung und Bestätigung eines
Mitarbeitercodes, Registrierungsbestätigung und erneuter Codeversand sowie die
Benutzerverwaltung sperren zuerst dieselbe `User`-Zeile mit `select_for_update()`.
Danach werden bei Bedarf Person und Verifikationsdatensatz gesperrt. Die Anmeldung
vergleicht die aktuell gesperrten Zugangsdaten mit dem tatsächlich geprüften
Passwortstand (`password`, `username`, `email`) und verlangt ein weiterhin aktives
Konto. Ein inzwischen geänderter Stand wird mit der neutralen Anmeldefehlermeldung
abgewiesen; Berechtigungen werden am frisch geladenen Konto geprüft. Auch die
Benutzerverwaltung verwendet den gesperrten aktuellen Kontostand statt eines
älteren Formularobjekts und prüft das neue Passwort bei Personenwechsel erneut.

Eine erfolgreiche Anmeldung speichert die authentifizierte Datenbanksitzung noch
innerhalb der Transaktion und unter der Kontosperre. Gewinnt die Anmeldung zuerst,
kann die anschließende Kontoänderung diese Sitzung bereits widerrufen. Gewinnt die
Kontoänderung zuerst, kann die Anmeldung keine Sitzung auf Grundlage veralteter
Zugangsdaten oder Rechte erzeugen. Ein späteres Speichern durch Djangos
`SessionMiddleware` aktualisiert ausschließlich die bestehende Sitzung; wurde sie
inzwischen gelöscht, bricht Django mit `SessionInterrupted` ab, statt sie neu
anzulegen. Ein bloßes erneutes Lesen des Kontos oder das bisherige einmalige Löschen
bereits gespeicherter Sitzungen würde diese Lücke nicht schließen. Eine zusätzliche
Kontoversion und ein eigenes Session-Middleware-Verfahren sind bei dieser
Synchronisierung mit dem bestehenden Django-Datenbank-Sessionbackend nicht nötig.

Die ausstehende MFA-Browsersitzung ist zusätzlich an den Hash des konkret
ausgestellten Codes gebunden. Eine ältere Passwortanmeldung kann dadurch keinen
Code einer späteren Anmeldung verwenden, auch wenn beide dasselbe Konto betreffen.
Ein veralteter Browser verwirft nur seinen eigenen ausstehenden Anmeldezustand und
verbraucht keine Versuche des neu ausgestellten Codes. Bereits vor dieser Änderung
begonnene MFA-Anmeldungen ohne diese Bindung müssen erneut gestartet werden.

Eine inaktive Selbstregistrierung mit vorhandenem `RegistrationVerification` ist
noch offen. Unverändertes Speichern erhält Hash, Ablaufzeit, Versuchszähler und
Versandsperre. Die Benutzerverwaltung bietet für diese Konten ausdrücklich
„Offene Registrierung widerrufen“ an; dieser Widerruf entfernt die Verifikation
und verhindert sowohl Bestätigung als auch erneuten Versand. Der Wechsel von
aktiv zu inaktiv sowie Änderungen an Zugangsdaten, Person oder Zugriffsrechten
verwerfen Codes weiterhin. `is_active=False` allein ist kein Widerruf, weil dieser
Wert bereits vor der ersten Bestätigung gilt.

## Erweiterungsroutine

Für eine neue geschützte Seite wird in dieser Reihenfolge vorgegangen:

1. Falls nötig, neue Permission in `Person.Meta.permissions`, `access.py` und der Rolleninitialisierung ergänzen.
2. Zuordnung zu einer Standardgruppe in der Rollenmatrix festlegen.
3. Den passenden fachlichen Decorator an jeder View einschließlich POST- und JSON-Endpunkten anbringen.
4. Navigation nur für Konten mit derselben Permission anzeigen.
5. Anonyme, unberechtigte und berechtigte Zugriffe als Django-Tests abdecken und diese ADR aktualisieren.

## Konsequenzen

- Nicht angemeldete Besucher sind ein Zugriffszustand, keine Rolle.
- Der Mieterbereich zeigt eigene bestätigte Übergabeprotokolle. Die Zuordnung erfolgt über `Protokoll.person.user`; die aktuelle Wohnung allein gewährt keinen Zugriff. Gemeinsame PDF-Endpunkte verwenden `handover_reader_required` und diese Objektprüfung. Abschluss und Bearbeitung bleiben Mitarbeitern vorbehalten (ADR-0014).
- Kontoerstellung, Registrierung und der Bootstrap-Command erzwingen die Personenverknüpfung. Verknüpfungslose Alt-Konten erhalten keinen Zugriff auf geschützte Bewerberdaten.
- Die E-Mail-Verifikation ist auf die Selbstregistrierung beschränkt. Passwort-Reset per E-Mail und Kontolöschung gehören nicht zum MVP.
