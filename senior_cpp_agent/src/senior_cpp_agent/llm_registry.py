from __future__ import annotations

import time
from dataclasses import asdict
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from langchain_core.messages import BaseMessage

from pydantic import SecretStr

from .config import AgentSettings, ModelRoute
from .runtime import RuntimeContext, role_output_to_artifact


class ModelInvocationError(RuntimeError):
    pass


class ChatModelFactory:
    """Creates role-specific chat models and executes with retry/fallback."""

    def __init__(self, settings: AgentSettings, runtime: RuntimeContext | None = None):
        self.settings = settings
        self.runtime = runtime

    def _create_model(self, route: ModelRoute):
        if route.provider == "openai":
            from langchain_openai import ChatOpenAI

            api_key = SecretStr(self.settings.openai_api_key) if self.settings.openai_api_key else None
            return ChatOpenAI(
                model=route.model,
                temperature=route.temperature,
                timeout=route.timeout_sec,
                api_key=api_key,
                base_url=self.settings.openai_base_url,
                max_retries=0,
            )
        raise ValueError(f"Unsupported provider: {route.provider}")

    def _create_agent(self, route: ModelRoute, tools: list[Any], prompt: str):
        from langgraph.prebuilt import create_react_agent

        return create_react_agent(model=self._create_model(route), tools=tools, prompt=prompt)

    def describe_routing(self) -> dict[str, list[dict[str, Any]]]:
        description: dict[str, list[dict[str, Any]]] = {}
        for role, routing in self.settings.role_routing.items():
            description[role] = [asdict(route) for route in routing.chain]
        return description

    def invoke_role(self, *, role: str, prompt: str, tools: list[Any], messages: list["BaseMessage"]):
        attempts = self.settings.llm_retry_attempts + 1
        errors: list[str] = []
        role_retries = 0
        role_errors = 0
        started_at = self.runtime.start_role_call(role) if self.runtime else None

        for route in self.settings.role_routing[role].chain:
            agent = self._create_agent(route, tools, prompt)
            for attempt_idx in range(1, attempts + 1):
                try:
                    output = agent.invoke({"messages": messages})
                    if self.runtime and started_at is not None:
                        self.runtime.complete_role_call(
                            role=role,
                            started_at=started_at,
                            retries=role_retries,
                            errors=role_errors,
                            usage=output.get("usage_metadata") or output.get("token_usage"),
                        )
                        artifact = role_output_to_artifact(output, role=role)
                        self.runtime.recorder.write_json(f"{role}_tool_output.json", artifact)
                    return output
                except Exception as exc:  # pragma: no cover - framework raises heterogeneous errors
                    role_errors += 1
                    errors.append(
                        f"role={role} provider={route.provider} model={route.model} "
                        f"attempt={attempt_idx}/{attempts} error={exc}"
                    )
                    if attempt_idx < attempts:
                        role_retries += 1
                        time.sleep(0.1 * attempt_idx)
                    else:
                        break

        if self.runtime and started_at is not None:
            self.runtime.complete_role_call(
                role=role,
                started_at=started_at,
                retries=role_retries,
                errors=role_errors,
                usage=None,
            )

        raise ModelInvocationError("All model routes failed: " + " | ".join(errors))
