# ADR 0026 · E-Mail-Benachrichtigungen

Die persönlichen Benachrichtigungen aus [#205](https://github.com/STEImmo/STEImmo/issues/205)
werden pro Konto und fachlicher Gruppe gespeichert. Bewerber und Mieter können den
Verwaltungsstandard übernehmen oder ausdrücklich An beziehungsweise Aus wählen.
Persönliches An und der Verwaltungsstandard erlauben nur eine administrativ freigegebene
Mailart. Persönliches Aus unterdrückt die gesamte Gruppe. Verwaltungsmails sind standardmäßig
aktiviert und folgen unabhängig davon der persönlichen Verwaltungsgruppe.

Die Freigaben liegen je Mailart im vorhandenen globalen Einstellungsdatensatz aus ADR 0024.
Die Migration überträgt einen gespeicherten Gesamtschalter auf alle bisherigen Mailarten.
Fehlende Freigaben starten aktiviert. Das ist eine Produktvoreinstellung. Gesperrte Kategorien
bleiben bei einem Rollenwechsel gespeichert. Die Formulare prüfen eine Version und das
globale Änderungsprotokoll nennt jede tatsächlich geänderte Mailart.

Die Versandwege prüfen zuerst den aktuellen Anlass und die fachliche Zugriffsberechtigung.
Danach prüfen sie unmittelbar vor jedem Zustellversuch die aktuellen Einstellungen. Bei
Terminbenachrichtigungen speichert das bestehende Ereignis den Zustand pro Empfängerkonto.
Nur fehlgeschlagene Empfänger werden erneut geprüft. Unterdrückte Ereignisse werden nach
erneuter Freigabe nicht nachgesendet. Die Hauptbewerbung verwendet ihren bestehenden
Ereignisverlauf für Versand, Fehler und Unterdrückung.

Sicherheitscodes, Rückrufrouting und ausdrücklich ausgelöste Vertragszustellung behalten
ihre eigenen Versandwege. Neue optionale Versandwege aus #201–#204 verwenden denselben
Katalog und dieselbe Einstellungsprüfung.
