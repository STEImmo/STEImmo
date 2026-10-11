# ADR-0017: Mobiler Schlüsselkopf im Übergabeformular

- Status: Accepted
- Datum: 2026-10-10
- Issue: #112

## Entscheidung

Der Kopf der Schlüsselübergabe im gemeinsamen Übergabeformular-Partial erhält die
vorhandene Klasse `handover-section-header`. Die bestehende Regel in `static/css/app.css`
ordnet Überschrift und Hinzufügen-Button bis 639 px untereinander mit Abstand und voller
Breite an. Ab 640 px bleibt die bestehende UIkit-Flex-Anordnung erhalten. Dies gilt sowohl
beim Anlegen als auch beim Bearbeiten eines Übergabeprotokolls.

Die Formularüberschrift verwendet zusätzlich UIkits `uk-text-break`, damit das lange Wort
„Übergabeprotokoll“ ebenfalls innerhalb der mobilen Seitenbreite umbricht.

## Warum

Ohne die mobile Regel sind Überschrift und Button zusammen breiter als der verfügbare
Formularinhalt. Auf dem aktuellen `main` wuchs bei 390 × 844 px die Dokumentbreite von
375 px auf 437 px; Tab zum ersten Stück-Feld verschob die Seite horizontal um rund 62 px.
Das vorhandene Layout für Übergabe-Abschnittsköpfe löst die Ursache ohne zusätzliche
CSS-Regeln oder Abhängigkeiten.
Die lange Formularüberschrift verursachte bei der ursprünglichen Reproduktion auf dem
Arbeitsbranch ebenfalls einen Überlauf. Ihr zusätzlicher Umbruch hält auch den Titel
innerhalb der verfügbaren Breite. Mit beiden Anpassungen bleibt die Dokumentbreite bei
390 × 844 px mit und ohne Tastaturfokus bei 375 px.

## Verworfen

- Globales Verbergen horizontalen Überlaufs: verdeckt unerreichbare Inhalte.
- Kleinere Schrift oder gekürzte Beschriftung: vermeidet keine zuverlässig zu breite Zeile.
- Eine weitere mobile CSS-Regel: dupliziert das bereits vorhandene Abschnittslayout.
