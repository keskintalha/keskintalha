from __future__ import annotations

import json
import os
from pathlib import Path

import typer
from dotenv import load_dotenv
from rich.console import Console
from rich.panel import Panel

from .config import AgentSettings, parse_role_routing_from_env
from .cpp_pipeline import CppPipeline
from .llm_registry import ChatModelFactory
from .orchestrator import SeniorCppAgent
from .runtime import RuntimeContext, tracing_enabled_from_env
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
        tracing_enabled=tracing_enabled_from_env(),
        tracing_project=os.getenv("LANGSMITH_PROJECT"),
    )


def _configure_tracing(settings: AgentSettings) -> None:
    if not settings.tracing_enabled:
        return
    os.environ.setdefault("LANGSMITH_TRACING", "true")
    os.environ.setdefault("LANGCHAIN_TRACING_V2", "true")
    if settings.tracing_project:
        os.environ.setdefault("LANGSMITH_PROJECT", settings.tracing_project)


@app.command()
def run(
    task: str = typer.Argument(..., help="Task for the agent, e.g. add tests for parser.cpp"),
    workspace: Path = typer.Option(Path.cwd(), "--workspace", "-w", help="Project root path"),
    profile: str = typer.Option("debug", "--profile", help="C++ pipeline profile (debug/release/asan/ubsan)"),
    output_json: bool = typer.Option(False, "--json", help="Print result as JSON"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Only resolve config/routing, do not call models"),
    model_dump: bool = typer.Option(False, "--model-dump", help="Print active role->model routing"),
    run_report: Path | None = typer.Option(None, "--run-report", help="Write reproducible run report JSON to this path"),
):
    """Run the full 4-LLM workflow (architect -> implementer -> reviewer -> validator)."""
    settings = _load_settings(workspace)
    _configure_tracing(settings)
    runtime = RuntimeContext(workspace=settings.workspace)
    routing = ChatModelFactory(settings).describe_routing()

    if model_dump or dry_run:
        console.print_json(
            json.dumps(
                {
                    "workspace": str(settings.workspace),
                    "routing": routing,
                    "request_id": runtime.request_id,
                    "run_id": runtime.run_id,
                    "tracing_enabled": settings.tracing_enabled,
                }
            )
        )

    if dry_run:
        raise typer.Exit(0)

    agent = SeniorCppAgent(settings, runtime=runtime)
    result = agent.run(task, profile=profile)
    report_payload = agent.create_run_report(result)

    payload = {
        **report_payload,
        "validation_result": report_payload["validation_result"],
        "pipeline_result": report_payload["pipeline_result"],
        "gate": report_payload["gate"],
        "repair_cycles_used": report_payload["repair_cycles_used"],
    }

    if run_report is not None:
        run_report.parent.mkdir(parents=True, exist_ok=True)
        run_report.write_text(json.dumps(report_payload, indent=2, ensure_ascii=False), encoding="utf-8")

    if output_json:
        console.print_json(json.dumps(payload))
        raise typer.Exit(0)

    console.print(Panel(result.architect_plan, title="1) Architecture Plan", border_style="cyan"))
    console.print(Panel(result.implementation_log, title="2) Implementation", border_style="green"))
    console.print(Panel(result.review_report, title="3) Review", border_style="yellow"))
    console.print(Panel(result.validation_report, title="4) Validation", border_style="magenta"))
    console.print(Panel(json.dumps(result.pipeline_result.to_dict(), indent=2), title="5) C++ Pipeline", border_style="blue"))

    gate_title = "6) Gate Status"
    gate_body = [
        f"merge_ready: {result.gate_result.merge_ready}",
        f"repair_cycles_used: {result.repair_cycles_used}",
        f"request_id: {result.request_id}",
        f"run_id: {result.run_id}",
        f"run_dir: {result.run_dir}",
    ]
    if result.gate_result.reasons:
        gate_body.append("reasons:")
        gate_body.extend(f"- {reason}" for reason in result.gate_result.reasons)
    console.print(Panel("\n".join(gate_body), title=gate_title, border_style="red" if not result.gate_result.merge_ready else "blue"))


@app.command("validate")
def validate_cmd(
    workspace: Path = typer.Option(Path.cwd(), "--workspace", "-w", help="Project root path"),
    profile: str = typer.Option("debug", "--profile", help="C++ pipeline profile (debug/release/asan/ubsan)"),
):
    """Run only the C++ validation pipeline for a profile."""
    settings = _load_settings(workspace)
    pipeline = CppPipeline(settings.workspace, settings.command_timeout_sec, profiles=settings.cpp_profiles)
    result = pipeline.run(profile)
    console.print_json(json.dumps(result.to_dict()))
    if not result.passed:
        raise typer.Exit(1)


@app.command("policy")
def policy_cmd():
    """Show allowed shell command prefixes for secure tool execution."""
    for cmd in sorted(SAFE_COMMAND_PREFIXES):
        console.print(f"- {cmd}")


if __name__ == "__main__":
    app()
