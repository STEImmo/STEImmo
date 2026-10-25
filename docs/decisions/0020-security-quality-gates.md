# ADR-0020: Schlanke Security Quality Gates in der CI

- Status: Angenommen
- Datum: 2026-10-25
- Bezug: [Issue #138](https://github.com/STEImmo/STEImmo/issues/138)

## Kontext

Die bestehenden Django-, Migrations-, Ruff- und Docker-Prüfungen erkennen
keine bekannten Schwachstellen in Python-Paketen und keine versehentlich
versionierten Secrets. Die Produktionssettings aus ADR-0018 sollen außerdem
schon im Pull Request geprüft werden, ohne Produktionszugriff zu benötigen.

## Entscheidung

Der bestehende wiederverwendbare Workflow `.github/workflows/ci.yml` erhält
folgende verpflichtende Prüfungen. Damit gelten sie sowohl für Pull Requests
nach `main` als auch beim Aufruf durch den Deployment-Workflow.

1. `python manage.py check --deploy --fail-level WARNING` verwendet die echten
   Produktionssettings mit ausdrücklich fiktiven CI-Werten und dem bereits im Job
   flüchtig erzeugten Django-Schlüssel. Der Schritt benötigt
   weder eine Datenbankverbindung noch SMTP-Zugriff oder GitHub-Secrets.
   Entwicklungssettings werden nicht für diesen Check nachgebaut.
2. Ein separater Security-Job installiert `.[dev]` mit Python 3.13 in einer
   temporären virtuellen Umgebung und protokolliert deren exakte Paketversionen.
   `pip-audit==2.10.1` läuft in einer zweiten Umgebung und prüft diesen Snapshot
   einschließlich transitiver Abhängigkeiten gegen PyPI. Scanner-Abhängigkeiten
   verändern daher nicht die geprüfte Projektumgebung. Nur das eigene, nicht auf
   PyPI veröffentlichte Paket `steimmo` wird aus dem Snapshot entfernt; seine
   Abhängigkeiten bleiben enthalten. `--strict` lässt auch nicht prüfbare Pakete
   fehlschlagen. Meldungen nennen Paket, Version, Advisory und bekannte
   Korrekturversionen; Beschreibungen helfen bei der Einordnung.
3. Gitleaks 8.30.1 wird als offizielles Containerimage mit unveränderlichem
   SHA-256-Digest ausgeführt. Ein vollständiger Checkout und `git --log-opts=--all`
   prüfen die lokal verfügbaren Git-Referenzen einschließlich der PR-Historie.
   Der Container hat ausschließlich lesenden Repositoryzugriff und kein Netzwerk.
   `--redact=100 --verbose` nennt Fundstelle und Regel, ohne Secretwerte auszugeben.
   Der Schritt läuft auch nach einem fehlgeschlagenen Dependency-Audit.

Die Jobs erhalten nur `contents: read`; Checkout speichert keine Zugangsdaten.
Es gibt weder `pull_request_target` noch Zugriff auf das Environment `deploy`.
Findings und Scannerfehler blockieren den jeweiligen Job; es gibt kein
`continue-on-error`, keine automatische Reparatur und keine globale Baseline.
Die bestehenden Qualitätsprüfungen bleiben erhalten. Bandit wird als optionaler
weiterer Scanner zunächst nicht eingeführt, um Umfang und Pflege klein zu halten.

Gitleaks dient als unabhängig von GitHub-Lizenz und Repository-Einstellungen
ausführbare Secret-Scanning-Alternative. Es ersetzt keine Push Protection:
ein Fund kann den Merge blockieren, aber keinen bereits erfolgten Push verhindern.
Repository-Einstellungen werden durch diese Änderung nicht verändert.

## Ausnahmen und Umgang mit Findings

- **Deploy-Check:** Die Produktionssettings unterdrücken ausschließlich
  `security.W004`, solange HSTS gemäß ADR-0018 vor dem ersten erfolgreichen
  öffentlichen HTTPS-Test bewusst deaktiviert bleibt. Die CI prüft genau diesen
  erlaubten Anfangszustand. Andere Warnungen bleiben Fehler. Für aktiviertes HSTS
  ist dessen vollständige Policy separat zu prüfen.
- **Dependency-Audit:** Zunächst keine Advisory-Ausnahmen. Bei einem Fund die
  betroffene direkte oder transitive Abhängigkeit gezielt aktualisieren und Tests
  wiederholen. Falls eine Ausnahme fachlich erforderlich ist, nur die konkrete
  Advisory-ID per `--ignore-vuln` zulassen und hier Paket, Begründung, verantwortliche
  Person sowie Überprüfungsdatum festhalten. Keine pauschale Unterdrückung
  nicht behebbarer Findings.
- **Secret-Scan:** Zunächst keine Ausnahmen, auch nicht für ganze Test- oder
  Dokumentationsverzeichnisse. Ein belegter False Positive darf nur mit genauer
  Fundstelle/Fingerprint oder einer auf Pfad und Wert begrenzten Regel sowie
  Begründung hier ausgenommen werden. Echte Secrets zuerst widerrufen/rotieren;
  bloßes Entfernen aus der aktuellen Datei beseitigt den historischen Fund nicht.

## Konsequenzen und Grenzen

Der erste Audit findet bekannte Schwachstellen in Pillow 11.3.0, das durch die
bisherige Obergrenze `<12` festgehalten wird. Deshalb wird ausschließlich dieser
Paketbereich auf `Pillow>=13.0.0,<14` angehoben. Pillow 13 unterstützt Python 3.13;
die Anwendung nutzt weiterhin `Image.open` und die Django-Bildvalidierung.
Der Updatebedarf wird nicht über Advisory-Ausnahmen verdeckt. Siehe
[Pillow-13-Release-Notes](https://pillow.readthedocs.io/en/stable/releasenotes/13.0.0.html)
und beispielsweise [CVE-2026-114501](https://github.com/advisories/GHSA-654x-cwwv-5j9c).

Die Scanner-Version bzw. der Containerdigest sind festgelegt. Das bestehende
Projekt löst Abhängigkeiten weiterhin aus Versionsbereichen in `pyproject.toml`
auf. Ein vollständiges Lock-/Hash-Verfahren bleibt eine separate Entscheidung;
dieser Change führt keine zweite handgepflegte Abhängigkeitsliste ein. Das Audit
prüft die in seinem Job tatsächlich aufgelösten Versionen. Ein späterer Lauf kann
wegen neuer Paketversionen oder aktualisierter Advisories anders ausfallen;
Netzwerk- und Dienstfehler werden nicht als erfolgreiche Prüfung gewertet.

## Lokale Validierung

- Aktueller `main`-Stand als Basis: Python 3.13, PostgreSQL 18.6 und Pillow 13.0.0;
  alle 775 Django-Tests unter Linux erfolgreich. Ausschließlich im lokalen
  Testprozess wird MD5 als schneller bevorzugter Passworthasher verwendet;
  PBKDF2 bleibt für die bestehenden Hash-Upgrade-Tests verfügbar. Die CI verwendet
  weiterhin unverändert die regulären Anwendungseinstellungen.
- 18 bestehende Betriebs-Skripttests, Ruff-Lint und Formatprüfung,
  Django-Systemcheck, Migrationsprüfung, Docker-Entwicklungsbuild, Actionlint und
  `git diff --check` erfolgreich.
- Produktionscheck im Linux-Container ohne Netzwerk erfolgreich; eine künstlich
  unsichere CSRF-Cookie-Einstellung wird mit `security.W016` und Exit-Code 1 blockiert.
- Dependency-Audit vor dem Pillow-Update mit Findings und Exit-Code 1, danach
  einschließlich der aktuellen PDF-Abhängigkeiten ohne bekannte Schwachstellen.
  Ein nicht auditierbares Paket wird mit `--strict` ebenfalls als Fehler behandelt.
- Gitleaks: alle 231 lokal vorhandenen Commits sowie der aktuelle PR-Dateistand
  ohne Fund. Ein erfundener GitHub-Token wird erkannt, vollständig maskiert und
  mit Exit-Code 1 blockiert.
- Der tatsächliche GitHub-Actions-Lauf wird am Pull Request ausgewiesen.

Quellen: [pip-audit](https://github.com/pypa/pip-audit),
[Gitleaks 8.30.1](https://github.com/gitleaks/gitleaks/blob/v8.30.1/README.md),
[offizielles Gitleaks-Image](https://github.com/gitleaks/gitleaks/pkgs/container/gitleaks).
