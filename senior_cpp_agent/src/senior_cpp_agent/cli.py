from __future__ import annotations

import json
import os
from pathlib import Path

import typer
from dotenv import load_dotenv
from rich.console import Console
from rich.panel import Panel

from .config import AgentSettings, parse_role_routing_from_env
from .llm_registry import ChatModelFactory
from .orchestrator import SeniorCppAgent
from .tools import SAFE_COMMAND_PREFIXES

app = typer.Typer(help="Senior C++ multi-LLM agent (LangChain)")
console = Console()


def _load_settings(workspace: Path) -> AgentSettings:
    load_dotenv()
    default_timeout = int(os.getenv("LLM_TIMEOUT_SEC", "60"))
    return AgentSettings(
        workspace=workspace,
        role_routing=parse_role_routing_from_env(default_timeout_sec=default_timeout),
        command_timeout_sec=int(os.getenv("COMMAND_TIMEOUT_SEC", "120")),
        llm_retry_attempts=int(os.getenv("LLM_RETRY_ATTEMPTS", "2")),
        max_repair_cycles=int(os.getenv("MAX_REPAIR_CYCLES", "0")),
        openai_api_key=os.getenv("OPENAI_API_KEY"),
        openai_base_url=os.getenv("OPENAI_BASE_URL"),
    )


@app.command()
def run(
    task: str = typer.Argument(..., help="Task for the agent, e.g. add tests for parser.cpp"),
    workspace: Path = typer.Option(Path.cwd(), "--workspace", "-w", help="Project root path"),
    output_json: bool = typer.Option(False, "--json", help="Print result as JSON"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Only resolve config/routing, do not call models"),
    model_dump: bool = typer.Option(False, "--model-dump", help="Print active role->model routing"),
):
    """Run the full 4-LLM workflow (architect -> implementer -> reviewer -> validator)."""
    settings = _load_settings(workspace)
    routing = ChatModelFactory(settings).describe_routing()

    if model_dump or dry_run:
        console.print_json(json.dumps({"workspace": str(settings.workspace), "routing": routing}))

    if dry_run:
        raise typer.Exit(0)

    agent = SeniorCppAgent(settings)
    result = agent.run(task)

    payload = {
        "architect_plan": result.architect_plan,
        "implementation_log": result.implementation_log,
        "review_report": result.review_report,
        "validation_report": result.validation_report,
        "validation_result": {
            "passed": result.validation_result.passed,
            "failed_checks": result.validation_result.failed_checks,
            "recommendations": result.validation_result.recommendations,
        },
        "gate": {
            "merge_ready": result.gate_result.merge_ready,
            "reasons": result.gate_result.reasons,
        },
        "repair_cycles_used": result.repair_cycles_used,
    }

    if output_json:
        console.print_json(json.dumps(payload))
        raise typer.Exit(0)

    console.print(Panel(result.architect_plan, title="1) Architecture Plan", border_style="cyan"))
    console.print(Panel(result.implementation_log, title="2) Implementation", border_style="green"))
    console.print(Panel(result.review_report, title="3) Review", border_style="yellow"))
    console.print(Panel(result.validation_report, title="4) Validation", border_style="magenta"))

    gate_title = "5) Gate Status"
    gate_body = [
        f"merge_ready: {result.gate_result.merge_ready}",
        f"repair_cycles_used: {result.repair_cycles_used}",
    ]
    if result.gate_result.reasons:
        gate_body.append("reasons:")
        gate_body.extend(f"- {reason}" for reason in result.gate_result.reasons)
    console.print(Panel("\n".join(gate_body), title=gate_title, border_style="red" if not result.gate_result.merge_ready else "blue"))


@app.command("policy")
def policy_cmd():
    """Show allowed shell command prefixes for secure tool execution."""
    for cmd in sorted(SAFE_COMMAND_PREFIXES):
        console.print(f"- {cmd}")


if __name__ == "__main__":
    app()
