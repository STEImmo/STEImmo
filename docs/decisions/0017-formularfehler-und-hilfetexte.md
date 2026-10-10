# ADR-0017: Feldbezogene Formularfehler und Hilfetexte

## Kontext

Django 5.2 ergänzt bei manuell gerenderten Formularfeldern automatisch
`aria-describedby` mit Kennungen für Fehler und Hilfetexte. Die eigenen
UIkit-Templates erzeugten diese Zielkennungen bisher nicht (Issue #111).

## Entscheidung

Der gemeinsame Template-Baustein `_form_field_feedback.html` rendert
Hilfetexte unter `<auto_id>_helptext` und alle Fehler eines Feldes in einem
Container unter `<auto_id>_error`. Präfixe von Formularen und Formsets bleiben
dadurch Bestandteil der Kennung. Feldgruppen erhalten den Beschreibungsverweis
am Fieldset, entsprechend dem Django-Verhalten für Radio- und Checkboxgruppen.

Die Zählerfelder des Übergabeformulars erscheinen in zwei umschaltbaren
Ansichten. Ihre Fehlerausgabe steht deshalb einmal unter beiden Ansichten,
damit beide Eingaben auf denselben sichtbaren Fehlercontainer verweisen.

## Konsequenzen

- Fehler und Hilfetexte sind mit den Eingaben verbunden; mehrere Fehler
  erzeugen keine mehrfach vergebenen Fehler-IDs.
- Registrierung, Bestätigungscodes, Verwaltung, Pre- und Main-Bewerbung und Übergaben
  verwenden denselben Baustein ohne zusätzliche Abhängigkeiten.
- Django-Response- und Template-Tests prüfen Zielkennungen, Fehlertexte,
  Labels, Feldgruppen und Präfixe. Ein Browsercheck ergänzt die Validierung.
