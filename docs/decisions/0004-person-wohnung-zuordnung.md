# ADR-0004: Direkte Person–Wohnung-Zuordnung

- Status: Accepted
- Datum: 2026-09-25
- Geltungsbereich: STEImmo-Django-Monolith

## Kontext

Für die Wohnungsübergabe muss die beteiligte Person direkt aus der gewählten Wohnung ermittelt werden. Das bisherige Datenmodell verknüpft Personen und Wohnungen ausschließlich über `Bewerbung`. Diese Verknüpfung beschreibt jedoch einen Bewerbungsprozess und keinen aktuellen Bewohnerstatus.

## Entscheidung

`Person` erhält eine optionale direkte Fremdschlüsselbeziehung zu `Wohnung`. Eine Wohnung kann mehrere Personen enthalten; eine Person ist für den MVP höchstens einer Wohnung direkt zugeordnet. Die Beziehung bleibt optional, damit Bewerber vor einer Wohnungszuteilung erfasst werden können.

Die Übergabeprotokollmaske lädt nach der Wohnungswahl ausschließlich die direkt zugeordneten Personen und validiert diese Einschränkung auch auf dem Server.

## Konsequenzen

- Übergabeprotokolle können keine fremde Person für eine Wohnung speichern.
- Bewerbungen bleiben unverändert als eigenständiger Prozess erhalten.
- Beim Löschen einer Wohnung wird die direkte Zuordnung einer Person aufgehoben; der Personenstammsatz bleibt bestehen.
