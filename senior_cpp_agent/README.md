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
ARCHITECT_MODEL=gpt-4.1
IMPLEMENTER_MODEL=gpt-4.1
REVIEWER_MODEL=gpt-4.1-mini
VALIDATOR_MODEL=gpt-4.1-mini
COMMAND_TIMEOUT_SEC=120
```

## CLI Nutzung

```bash
cpp-agent policy
cpp-agent run "Füge Unit Tests für src/parser.cpp hinzu und führe ctest aus" --workspace /path/to/repo
cpp-agent run "Refactore memory handling in engine.cpp" --workspace . --json
```

## Architektur

- `SeniorCppAgent` orchestriert 4 nacheinander ausgeführte LangChain-Agenten.
- Jeder Agent bekommt dieselben professionellen Tools:
  - `read_file`
  - `write_file`
  - `run_command` (mit Allowlist)

## Sicherheit / Professionalität

`run_command` akzeptiert nur freigegebene Build/Test-Kommandos (`cmake`, `ctest`, `make`, `ninja`, `g++`, `clang++`, `pytest`, ...). Das reduziert Risiko in CI/Prod-ähnlichen Umgebungen.

## Tests

```bash
pytest
```
