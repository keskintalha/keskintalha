# Senior C++ Developer AI Agent (Python + LangChain)

Dieses Projekt liefert einen **professionellen Multi-LLM Agenten** für C++-Entwicklung mit LangChain.

## CI- und Quality-Standards (verbindlich)

Alle Pull Requests müssen folgende Gates bestehen:

- Lint: `ruff check .`
- Type-Checks: `mypy src`
- Tests: `pytest --cov=src --cov-report=term-missing`
- Packaging: `python -m build` + `twine check dist/*`
- Dependency-Scan: `pip-audit --strict`
- Secret-Scanning: `gitleaks`
- Dependency-Review (GitHub Action auf PRs)

Die Workflows liegen unter `.github/workflows/`.

## Release-Strategie

- **Versionierung:** Semantic Versioning (SemVer)
- **Changelog:** `CHANGELOG.md` nach Keep-a-Changelog-Struktur
- **Release Notes:** Werden aus dem Changelog und PR-Zusammenfassungen abgeleitet

## Erfüllt deine 4 Anforderungen

1. **LangChain als Framework** (aktuelle Paketlinien über `>=` Versionen).
2. **4 LLM-Rollen**:
   - Architect
   - Implementer
   - Reviewer
   - Validator
3. **Industrie-tauglicher Workflow** mit klarer Rollenverteilung, Tooling und Sicherheits-Policy.
4. **CLI Interface** für professionelle Ausführung von Aufgaben (Dateien ändern, Tests ausführen, Builds triggern).

## Toolchain-Voraussetzungen

Für die neue C++-Pipeline werden folgende Tools erwartet:

- `cmake` (Configure + Build)
- `ctest` (Test-Ausführung)
- `clang-tidy` (Linting)
- C/C++ Compiler (`clang++` oder `g++`)
- optional für Sanitizer-Profile: Toolchain mit `-fsanitize=address` / `-fsanitize=undefined`

Empfehlung: CMake-Projekt sollte ein `clang-tidy`-Target bzw. `CMAKE_CXX_CLANG_TIDY` unterstützen.

## Installation

```bash
cd senior_cpp_agent
python -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -e .[dev]
```

## Konfiguration

Lege eine `.env` an:

```dotenv
OPENAI_API_KEY=...
COMMAND_TIMEOUT_SEC=120
LLM_TIMEOUT_SEC=60
MAX_REPAIR_CYCLES=1

# Optionales Tracing (LangChain/LangSmith-kompatibel)
SENIOR_CPP_AGENT_TRACING=true
LANGSMITH_PROJECT=senior-cpp-agent
LANGSMITH_API_KEY=...
```

Die Agent-Konfiguration enthält C++ Build-Profile:

- `debug`
- `release`
- `asan`
- `ubsan`

## CLI Nutzung

```bash
cpp-agent policy
cpp-agent run "Füge Unit Tests für src/parser.cpp hinzu und führe ctest aus" --workspace /path/to/repo
cpp-agent run "Refactore memory handling in engine.cpp" --workspace . --profile asan --json
cpp-agent run "Harden CI build" --workspace . --run-report ./artifacts/run-report.json
cpp-agent validate --workspace . --profile release
```

`--run-report <path>` schreibt einen reproduzierbaren JSON-Report mit Request-ID, Run-ID, Metriken, Gate-Status und Pipeline-Ergebnissen.

## Runtime-Observability

- **Strukturiertes Logging (JSON)** pro Lauf mit `request_id` und `run_id`.
- **Metriken je Rolle**: Tokenverbrauch, Latenz, Fehler und Retries.
- **Optionales Tracing** per Environment-Flag (`SENIOR_CPP_AGENT_TRACING=true`) und LangSmith-Variablen.
- **Run-Artefakte** liegen unter `.senior_cpp_agent/runs/<run_id>/` (Prompts, Entscheidungen, Tool-Outputs, Pipeline/Run-Summary).

## Datenschutz & Retention

Run-Artefakte werden datenschutzkonform gespeichert:

- Sensible Felder (z. B. `api_key`, `token`, `secret`, `password`, `authorization`) werden vor Persistierung maskiert (`[REDACTED]`).
- Standardmäßig bleiben Artefakte lokal im Workspace (`.senior_cpp_agent/runs/`).
- Empfohlene Retention-Policy: 
  - Dev-Umgebung: automatische Löschung nach 7–14 Tagen.
  - CI: nur bei Fehlerfällen archivieren, sonst nach erfolgreichem Lauf löschen.
  - Produktivnahe Umgebungen: striktes Least-Privilege auf das Run-Verzeichnis und geplantes Purging (z. B. täglicher Cron).
- Für GDPR/DSGVO: keine personenbezogenen Daten in Prompts/Tool-Outputs einbetten; falls unvermeidbar, vor Verarbeitung pseudonymisieren.

## Architektur

- `SeniorCppAgent` orchestriert 4 nacheinander ausgeführte LangChain-Agenten.
- Zusätzlich läuft eine strukturierte C++ Pipeline (`configure`, `build`, `test`, `lint`, optional `sanitizer`).
- Pipeline-Resultate werden als Validator-Input injiziert, damit Entscheidungen auf realen Checks basieren.

## Sicherheit / Professionalität

`run_command` akzeptiert nur freigegebene Build/Test-Kommandos (`cmake`, `ctest`, `make`, `ninja`, `clang-tidy`, `g++`, `clang++`, `pytest`, ...). Das reduziert Risiko in CI/Prod-ähnlichen Umgebungen.

## Tests

```bash
pytest
```
