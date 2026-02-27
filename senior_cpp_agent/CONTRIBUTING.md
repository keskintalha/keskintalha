# Contributing

Vielen Dank für Beiträge zu `senior-cpp-agent`.

## Branching-Strategie

- `main` bleibt jederzeit releasable.
- Arbeite in kurzen Feature-Branches ab `main`.
- Branch-Namensschema:
  - `feat/<kurzbeschreibung>`
  - `fix/<kurzbeschreibung>`
  - `chore/<kurzbeschreibung>`
  - `docs/<kurzbeschreibung>`

## Commit- und Versionskonvention

- Commit Messages sollten sich an **Conventional Commits** orientieren (`feat:`, `fix:`, `chore:`, ...).
- Versionierung folgt **SemVer**:
  - `MAJOR`: Breaking Changes
  - `MINOR`: Rückwärtskompatible Features
  - `PATCH`: Rückwärtskompatible Bugfixes
- Jede User-Visible Änderung benötigt einen Changelog-Eintrag unter `CHANGELOG.md`.

## Pull-Request-Regeln

1. Nutze das PR-Template vollständig.
2. Halte PRs klein und fokussiert.
3. Verlinke Issues/Tickets bei vorhandenem Kontext.
4. Dokumentiere Risiken, Testnachweise und Rollback.

## Pflicht-Gates (CI)

Folgende Checks müssen grün sein, bevor gemerged wird:

- `ruff check .`
- `mypy src`
- `pytest --cov=src --cov-report=term-missing`
- `python -m build`
- `twine check dist/*`
- `pip-audit --strict`
- Secret-Scanning (gitleaks)
- Dependency-Review auf PRs

## Review-Regeln

- Mindestens **ein Review** ist erforderlich.
- Bei Änderungen an Build/CI/Security wird ein Review von Maintainer:innen empfohlen.
- Kein Self-Merge bei offenen "request changes".

## Lokales Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -e .[dev]
```

## Lokale Qualitätsprüfung vor PR

```bash
ruff check .
mypy src
pytest --cov=src --cov-report=term-missing
python -m build
twine check dist/*
pip-audit --strict
```
