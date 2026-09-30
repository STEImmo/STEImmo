# ADR-0008: Rollen und Zugriffskontrolle

## Kontext

STEImmo benötigt geschützte Bewerbungsdaten, einen Mitarbeiterbereich für Stammdaten und Übergaben sowie eine kontrollierte Pflege von Konten und Seitenrechten. Jede Person kann ohne Konto bestehen; jedes über die Anwendung angelegte Konto ist jedoch genau einer Person zugeordnet.

## Entscheidung

Django `User`, `Group` und `Permission` bilden die technische Grundlage. Die fachlichen Codenames und Decorators liegen zentral in `wohnungsverwaltung.access`; Views verwenden ausschließlich diese Decorators. Navigationslinks werden anhand derselben Berechtigungen angezeigt, ersetzen aber nie den serverseitigen Schutz.

| Zugriff | Django-Gruppe | Berechtigung | Aktuelle Seiten |
|---|---|---|---|
| Öffentlich | keine | keine | Startseite, Gesundheitscheck, Bewerbungsvorschau, Anmeldung, Registrierung |
| Bewerber | `Bewerber` | `access_applicant_area` | eigene Pre-Bewerbungen erstellen und einsehen |
| Mieter | `Mieter` | `access_tenant_area` | vorbereitet; noch keine Seite im MVP-Stand |
| Mitarbeiter | `Mitarbeiter` | `access_employee_area` | Verwaltung und alle Übergabeprotokoll-Endpunkte |
| Benutzerverwaltung | `Benutzerverwaltung` | `access_employee_area`, `manage_user_accounts` | zusätzlich Konto-, Rollen- und Rechteverwaltung |

Gruppen definieren die Standardrollen. Die vier Seitenrechte können zusätzlich direkt einem einzelnen Konto zugeordnet werden. Beim Übergang vom Bewerber zum Mieter bleibt die Bewerbergruppe bestehen; die Mietergruppe wird ergänzt.

Die Rollen und Permissions werden über Migration und idempotent nach `post_migrate` angelegt. Damit stehen sie auch nach einem Django-Testdatenbank-Flush zuverlässig bereit. Bestehende, mit einer Person verknüpfte Konten erhalten bei der Migration abhängig von `Person.is_employee` die Gruppe `Bewerber` oder `Mitarbeiter`.

Die UIkit-Benutzerverwaltung ist der einzige Pflegeweg für User und Gruppen in der Anwendung. Sie kann eine vorhandene konto-lose Person zuordnen oder eine neue Person samt Konto erstellen. Konten werden nur deaktiviert, nicht gelöscht. Der Django-Admin registriert `User` und `Group` nicht, damit keine parallele Kontoanlage ohne Personenbezug entsteht.

## Erweiterungsroutine

Für eine neue geschützte Seite wird in dieser Reihenfolge vorgegangen:

1. Falls nötig, neue Permission in `Person.Meta.permissions`, `access.py` und der Rolleninitialisierung ergänzen.
2. Zuordnung zu einer Standardgruppe in der Rollenmatrix festlegen.
3. Den passenden fachlichen Decorator an jeder View einschließlich POST- und JSON-Endpunkten anbringen.
4. Navigation nur für Konten mit derselben Permission anzeigen.
5. Anonyme, unberechtigte und berechtigte Zugriffe als Django-Tests abdecken und diese ADR aktualisieren.

## Konsequenzen

- Nicht angemeldete Besucher sind ein Zugriffszustand, keine Rolle.
- Der Mieterbereich ist bewusst nur vorbereitet; eine spätere User Story definiert seine Seiten und Datenfreigaben.
- Kontoerstellung, Registrierung und der Bootstrap-Command erzwingen die Personenverknüpfung. Verknüpfungslose Alt-Konten erhalten keinen Zugriff auf geschützte Bewerberdaten.
- E-Mail-Verifikation, Passwort-Reset per E-Mail und Kontolöschung gehören nicht zum MVP.
