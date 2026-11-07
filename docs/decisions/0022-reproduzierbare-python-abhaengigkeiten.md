# ADR-0022: Reproduzierbare Python-Abhängigkeiten

- Status: Angenommen
- Datum: 2026-11-04
- Bezug: [Issue #137](https://github.com/STEImmo/STEImmo/issues/137)

## Entscheidung

`pyproject.toml` bleibt die Quelle der direkten Runtime- und Dev-Anforderungen.
Die daraus generierten `requirements/runtime.txt` und `requirements/dev.txt`
enthalten exakte Versionen, transitive Abhängigkeiten, Plattformmarker und
SHA-256-Prüfsummen. Die vollständige Dev-Liste wird gegen die Runtime-Liste
aufgelöst, damit gemeinsame Pakete dieselben Versionen verwenden.
`requirements/build.in` und die generierte `requirements/build.txt` erfassen
Setuptools, Wheel und deren Abhängigkeiten für den lokalen Projektbuild.
Gemeinsame Build-/Runtime-Pakete werden ebenfalls auf dieselbe Version begrenzt.

Die Listen werden mit `uv==0.13.7` für Python 3.13 universell erzeugt. Das Werkzeug
ist ausschließlich eine Dev-Abhängigkeit (MIT/Apache-2.0, aktiv gepflegtes Projekt).
Sein konkreter Nutzen ist die Auflösung von Plattformmarkern für Windows und Linux
in einer gemeinsamen Liste; `pip freeze` bildet nur eine installierte Umgebung ab.
Eine eigene Auflösung mit der Standardbibliothek wäre unnötig komplex.
Es entsteht weder ein zusätzlicher Anwendungsdienst noch ein zweiter Paketmanager
zur Laufzeit: Docker und CI installieren weiterhin mit pip.

Installationen verwenden `--require-hashes --only-binary=:all:`. Fehlende passende
Wheels oder unpassende Prüfsummen brechen die Installation ab. Das eigene lokale
Paket wird anschließend mit `--no-deps --no-build-isolation` gebaut, damit keine
ungeprüften Build- oder Runtime-Abhängigkeiten nachgeladen werden. `pip check`
prüft die resultierenden Paketanforderungen. Nur der eigene Quellcode wird lokal
gebaut; heruntergeladene Pakete werden nicht aus Quelldistributionen gebaut.

CI prüft durch erneute Auflösung unter den versionierten Constraints und
Dateivergleich, dass Projektdefinition und Listen übereinstimmen. Die getrennte
Audit-Umgebung installiert dieselben Build- und Dev-Listen mit Prüfsummenprüfung.
Der bestehende Scanner prüft deren tatsächlich installierte Versionen einschließlich
Buildwerkzeugen; Scanner-Abhängigkeiten bleiben in einer separaten Umgebung.
Dies ersetzt die freie Auflösung aus ADR-0020.

## Installation ohne Docker (Python 3.13, virtuelle Umgebung)

```bash
python -m pip install --require-hashes --only-binary=:all: -r requirements/build.txt
python -m pip install --require-hashes --only-binary=:all: -r requirements/dev.txt
python -m pip install --no-deps --no-build-isolation ".[dev]"
python -m pip check
```

Für reine Runtime-Installationen `runtime.txt` statt `dev.txt` und `.` statt
`.[dev]` verwenden. Die reguläre lokale Entwicklung erfolgt weiterhin mit Docker.

## Kontrollierte Updates

1. Auf einem eigenen Issue-Branch die direkten Anforderungen in `pyproject.toml`
   beziehungsweise `requirements/build.in` bei Bedarf anpassen. Generierte Listen
   nicht von Hand editieren. Das Dev-Image enthält die festgelegte uv-Version;
   alternativ die oben beschriebene virtuelle Umgebung verwenden.
2. Im Repository mit Python 3.13 die Listen in dieser Reihenfolge neu erzeugen:

   ```bash
   uv pip compile pyproject.toml --universal --python-version 3.13 --generate-hashes --no-header --no-annotate --output-file requirements/runtime.txt
   uv pip compile pyproject.toml --extra dev --constraint requirements/runtime.txt --universal --python-version 3.13 --generate-hashes --no-header --no-annotate --output-file requirements/dev.txt
   uv pip compile requirements/build.in --constraint requirements/runtime.txt --universal --python-version 3.13 --generate-hashes --no-header --no-annotate --output-file requirements/build.txt
   ```

   Ohne Updateoption erhält uv passende bestehende Versionen. Für ein gezieltes
   Update `--upgrade-package PAKET` beim betreffenden Aufruf ergänzen. Für ein
   bewusstes vollständiges Update `--upgrade` bei allen drei Aufrufen ergänzen.
   Änderungen eines gemeinsamen Pakets zuerst in der Runtime-Liste durchführen.
   Bei Änderung der uv-Version zuerst die neue Version separat installieren und
   damit die Dev-Liste neu erzeugen.
3. Versions-, Marker- und Hashänderungen im Diff prüfen. Beide Docker-Targets neu
   bauen, Django-Tests, System-/Migrationschecks und Ruff ausführen. Bei Windows-
   Unterstützung zusätzlich eine frische Windows-Installation prüfen.
4. Vor Freigabe den Security-Job erfolgreich ausführen. Lokal entsprechend:

   ```bash
   python -m pip list --format=freeze --exclude steimmo > audit-requirements.txt
   python -m venv /tmp/steimmo-audit-tool
   /tmp/steimmo-audit-tool/bin/python -m pip install pip-audit==2.10.1
   /tmp/steimmo-audit-tool/bin/python -m pip_audit --requirement audit-requirements.txt --no-deps --disable-pip --strict --progress-spinner off --desc on
   ```

   Diesen Snapshot aus einer frischen Umgebung mit Build- und Dev-Liste erzeugen,
   nicht aus einer mit anderen Werkzeugen vermischten Umgebung. Der `/tmp`-Pfad
   gilt für Linux; unter Windows eine separate temporäre Umgebung und deren
   `Scripts/python.exe` verwenden. Audit-Snapshot nicht committen.
   Findings beheben und Listen/Tests erneut prüfen; Ausnahmen folgen ADR-0020.
5. Projektdefinition, alle betroffenen generierten Listen und Prüfergebnisse im
   selben PR reviewen. Erst nach erfolgreicher CI freigeben.

## Grenzen

Reproduziert werden Python-Paketversionen und erlaubte Distributionsdateien,
keine bitidentischen Docker-Images. Basisimage, Python-Patchversion, Betriebssystem
und der mit Python ausgelieferte pip sind nicht Teil dieses Paketlocks. Marker
erlauben notwendige Unterschiede wie `tzdata` ausschließlich unter Windows.
Neue Wheels derselben Paketversion verändern eine neu erzeugte Hashliste und
werden erst durch einen geprüften Commit zugelassen. Netzwerk- und Auditfehler
gelten nicht als erfolgreiche Sicherheitsprüfung.

## Validierung am 04.11.2026

- Runtime- und Entwicklungsimage unter Linux mit Python 3.13 erfolgreich gebaut;
  zusätzlich frische Windows-Installation aus Build-/Dev-Liste und `pip check`
  erfolgreich. Alle aktiven Windows-Paketpins gegen die installierten Versionen geprüft.
- Alle drei Listen unter Linux mit den CI-Befehlen bytegleich neu erzeugt.
  Alle 15 gemeinsamen installierten Pakete beider Images haben identische Versionen;
  uv und Ruff sind ausschließlich im Entwicklungsimage installiert.
- Manipulierte SHA-256-Prüfsumme wird durch pip abgewiesen. Eine temporär auf
  Django 6 geänderte Projektanforderung scheitert an den Runtime-Constraints.
- 915 Django-Tests auf isoliertem PostgreSQL 18.6 und 18 Betriebs-Skripttests
  erfolgreich; Django-Systemcheck, Migrationsprüfung, Produktionscheck und Ruff
  erfolgreich. Der Produktionscheck verwendet fiktive Werte und die bestehende,
  dokumentierte HSTS-Ausnahme aus ADR-0018.
- `pip-audit==2.10.1` prüft den tatsächlich installierten Linux-Build-/Dev-Stand
  in einer getrennten Scannerumgebung: keine bekannten Schwachstellen gefunden.
  Ein tatsächlicher GitHub-Actions-Lauf steht bis zur Veröffentlichung des PR aus.

Quellen: [uv: universelle Auflösung und Hashlisten](https://docs.astral.sh/uv/pip/compile/),
[pip: sichere Installationen](https://pip.pypa.io/en/stable/topics/secure-installs/),
[uv: Lizenz und Projekt](https://github.com/astral-sh/uv).
