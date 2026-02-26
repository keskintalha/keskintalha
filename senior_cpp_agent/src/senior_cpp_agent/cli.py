from __future__ import annotations

import json
import os
from pathlib import Path

import typer
from dotenv import load_dotenv
from rich.console import Console
from rich.panel import Panel

from .config import AgentSettings
from .orchestrator import SeniorCppAgent
from .tools import SAFE_COMMAND_PREFIXES

app = typer.Typer(help="Senior C++ multi-LLM agent (LangChain)")
console = Console()


def _load_settings(workspace: Path) -> AgentSettings:
    load_dotenv()
    return AgentSettings(
        workspace=workspace,
        architect_model=os.getenv("ARCHITECT_MODEL", "gpt-4.1"),
        implementer_model=os.getenv("IMPLEMENTER_MODEL", "gpt-4.1"),
        reviewer_model=os.getenv("REVIEWER_MODEL", "gpt-4.1-mini"),
        validator_model=os.getenv("VALIDATOR_MODEL", "gpt-4.1-mini"),
        command_timeout_sec=int(os.getenv("COMMAND_TIMEOUT_SEC", "120")),
    )


@app.command()
def run(
    task: str = typer.Argument(..., help="Task for the agent, e.g. add tests for parser.cpp"),
    workspace: Path = typer.Option(Path.cwd(), "--workspace", "-w", help="Project root path"),
    output_json: bool = typer.Option(False, "--json", help="Print result as JSON"),
):
    """Run the full 4-LLM workflow (architect -> implementer -> reviewer -> validator)."""
    settings = _load_settings(workspace)
    agent = SeniorCppAgent(settings)
    result = agent.run(task)

    payload = {
        "architect_plan": result.architect_plan,
        "implementation_log": result.implementation_log,
        "review_report": result.review_report,
        "validation_report": result.validation_report,
    }

    if output_json:
        console.print_json(json.dumps(payload))
        raise typer.Exit(0)

    console.print(Panel(result.architect_plan, title="1) Architecture Plan", border_style="cyan"))
    console.print(Panel(result.implementation_log, title="2) Implementation", border_style="green"))
    console.print(Panel(result.review_report, title="3) Review", border_style="yellow"))
    console.print(Panel(result.validation_report, title="4) Validation", border_style="magenta"))


@app.command("policy")
def policy_cmd():
    """Show allowed shell command prefixes for secure tool execution."""
    for cmd in sorted(SAFE_COMMAND_PREFIXES):
        console.print(f"- {cmd}")


if __name__ == "__main__":
    app()
