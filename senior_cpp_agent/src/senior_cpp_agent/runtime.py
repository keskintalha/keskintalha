from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from uuid import uuid4

SENSITIVE_KEY_PATTERN = re.compile(r"(api[_-]?key|token|secret|password|authorization)", re.IGNORECASE)


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": getattr(record, "request_id", None),
            "run_id": getattr(record, "run_id", None),
            "event": getattr(record, "event", None),
        }
        for key, value in payload.copy().items():
            if value is None:
                payload.pop(key, None)
        return json.dumps(payload, ensure_ascii=False)


class ContextAdapter(logging.LoggerAdapter):
    def process(self, msg, kwargs):
        extra = kwargs.setdefault("extra", {})
        extra.setdefault("request_id", self.extra["request_id"])
        extra.setdefault("run_id", self.extra["run_id"])
        return msg, kwargs


@dataclass(slots=True)
class RoleMetric:
    role: str
    calls: int = 0
    retries: int = 0
    errors: int = 0
    total_latency_ms: float = 0.0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0

    def to_dict(self) -> dict[str, int | float | str]:
        error_rate = self.errors / self.calls if self.calls else 0.0
        avg_latency = self.total_latency_ms / self.calls if self.calls else 0.0
        return {
            "role": self.role,
            "calls": self.calls,
            "retries": self.retries,
            "errors": self.errors,
            "error_rate": round(error_rate, 4),
            "total_latency_ms": round(self.total_latency_ms, 2),
            "avg_latency_ms": round(avg_latency, 2),
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens,
        }


@dataclass(slots=True)
class RunRecorder:
    run_dir: Path

    def __post_init__(self) -> None:
        self.run_dir.mkdir(parents=True, exist_ok=True)

    def write_json(self, name: str, payload: dict | list) -> Path:
        path = self.run_dir / name
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        return path

    def write_text(self, name: str, payload: str) -> Path:
        path = self.run_dir / name
        path.write_text(payload, encoding="utf-8")
        return path


@dataclass(slots=True)
class RuntimeContext:
    workspace: Path
    request_id: str = field(default_factory=lambda: uuid4().hex)
    run_id: str = field(default_factory=lambda: uuid4().hex)
    metrics: dict[str, RoleMetric] = field(default_factory=dict)
    decisions: list[dict[str, str | int | bool]] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.workspace = self.workspace.expanduser().resolve()

    @property
    def recorder(self) -> RunRecorder:
        return RunRecorder(self.workspace / ".senior_cpp_agent" / "runs" / self.run_id)

    def logger(self) -> ContextAdapter:
        base_logger = logging.getLogger("senior_cpp_agent.runtime")
        if not base_logger.handlers:
            handler = logging.StreamHandler()
            handler.setFormatter(JsonFormatter())
            base_logger.addHandler(handler)
            base_logger.setLevel(logging.INFO)
            base_logger.propagate = False
        return ContextAdapter(base_logger, {"request_id": self.request_id, "run_id": self.run_id})

    def metric(self, role: str) -> RoleMetric:
        if role not in self.metrics:
            self.metrics[role] = RoleMetric(role=role)
        return self.metrics[role]

    def start_role_call(self, role: str) -> float:
        self.metric(role).calls += 1
        return perf_counter()

    def complete_role_call(
        self,
        *,
        role: str,
        started_at: float,
        retries: int,
        errors: int,
        usage: dict[str, int] | None,
    ) -> None:
        metric = self.metric(role)
        metric.retries += retries
        metric.errors += errors
        metric.total_latency_ms += (perf_counter() - started_at) * 1000.0
        if usage:
            metric.prompt_tokens += int(usage.get("input_tokens", usage.get("prompt_tokens", 0)))
            metric.completion_tokens += int(usage.get("output_tokens", usage.get("completion_tokens", 0)))
            metric.total_tokens += int(usage.get("total_tokens", 0))

    def add_decision(self, *, stage: str, decision: str, success: bool) -> None:
        self.decisions.append({"stage": stage, "decision": decision, "success": success})

    def artifacts_snapshot(self) -> dict:
        return {
            "request_id": self.request_id,
            "run_id": self.run_id,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "metrics": {role: metric.to_dict() for role, metric in self.metrics.items()},
            "decisions": list(self.decisions),
        }


def sanitize_payload(value):
    if isinstance(value, dict):
        redacted: dict[str, object] = {}
        for key, item in value.items():
            if SENSITIVE_KEY_PATTERN.search(str(key)):
                redacted[key] = "[REDACTED]"
            else:
                redacted[key] = sanitize_payload(item)
        return redacted
    if isinstance(value, list):
        return [sanitize_payload(item) for item in value]
    if isinstance(value, tuple):
        return [sanitize_payload(item) for item in value]
    return value


def role_output_to_artifact(output: dict, role: str) -> dict:
    messages = []
    for msg in output.get("messages", []):
        messages.append(
            {
                "type": getattr(msg, "type", msg.__class__.__name__),
                "content": getattr(msg, "content", str(msg)),
            }
        )

    usage = sanitize_payload(output.get("usage_metadata") or output.get("token_usage") or {})
    return {
        "role": role,
        "messages": sanitize_payload(messages),
        "usage": usage,
        "raw": sanitize_payload({k: v for k, v in output.items() if k != "messages"}),
    }


def tracing_enabled_from_env() -> bool:
    return os.getenv("SENIOR_CPP_AGENT_TRACING", "false").lower() in {"1", "true", "yes", "on"}
