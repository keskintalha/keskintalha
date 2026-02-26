# Senior C++ Developer AI Agent (Python + LangChain)

Dieses Projekt liefert einen **professionellen Multi-LLM Agenten** für C++-Entwicklung mit LangChain.

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
cpp-agent validate --workspace . --profile release
```

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
