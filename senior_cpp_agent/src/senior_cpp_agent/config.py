from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

ROLES = ("architect", "implementer", "reviewer", "validator")
SUPPORTED_PROVIDERS = {"openai"}


@dataclass(frozen=True, slots=True)
class ModelRoute:
    """Provider-agnostic model target."""

    provider: str
    model: str
    temperature: float = 0.0
    timeout_sec: int = 60

    def __post_init__(self) -> None:
        if self.provider not in SUPPORTED_PROVIDERS:
            raise ValueError(f"Unsupported provider: {self.provider}")
        if not self.model.strip():
            raise ValueError("model must not be empty")
        if not (0 <= self.temperature <= 2):
            raise ValueError("temperature must be between 0 and 2")
        if not (1 <= self.timeout_sec <= 600):
            raise ValueError("timeout_sec must be between 1 and 600")


@dataclass(frozen=True, slots=True)
class RoleRouting:
    primary: ModelRoute
    fallbacks: tuple[ModelRoute, ...] = ()

    @property
    def chain(self) -> tuple[ModelRoute, ...]:
        return (self.primary, *self.fallbacks)


@dataclass(slots=True)
class AgentSettings:
    """Runtime configuration for the C++ agent."""

    workspace: Path
    role_routing: dict[str, RoleRouting] = field(default_factory=dict)
    command_timeout_sec: int = 120
    llm_retry_attempts: int = 2
    openai_api_key: str | None = None
    openai_base_url: str | None = None

    def __post_init__(self) -> None:
        self.workspace = self.workspace.expanduser().resolve()
        if not self.workspace.exists() or not self.workspace.is_dir():
            raise ValueError(f"Workspace does not exist or is not a directory: {self.workspace}")
        if not (1 <= self.command_timeout_sec <= 900):
            raise ValueError("command_timeout_sec must be between 1 and 900")
        if not (0 <= self.llm_retry_attempts <= 5):
            raise ValueError("llm_retry_attempts must be between 0 and 5")

        if not self.role_routing:
            self.role_routing = default_role_routing()

        missing_roles = set(ROLES) - set(self.role_routing)
        if missing_roles:
            raise ValueError(f"Missing role routing configuration for: {sorted(missing_roles)}")

        used_providers = {route.provider for routing in self.role_routing.values() for route in routing.chain}
        if "openai" in used_providers and not (self.openai_api_key and self.openai_api_key.strip()):
            raise ValueError("OPENAI_API_KEY is required when OpenAI models are configured")



def _parse_route_item(item: str, default_timeout_sec: int, default_temperature: float) -> ModelRoute:
    # format: provider:model[@temperature][:timeout]
    spec = item.strip()
    if not spec:
        raise ValueError("Empty route entry")

    timeout_sec = default_timeout_sec
    if ":" in spec and spec.count(":") >= 2:
        spec, timeout_part = spec.rsplit(":", 1)
        timeout_sec = int(timeout_part)

    temperature = default_temperature
    if "@" in spec:
        spec, temperature_part = spec.rsplit("@", 1)
        temperature = float(temperature_part)

    provider, model = spec.split(":", 1)
    return ModelRoute(
        provider=provider.strip().lower(),
        model=model.strip(),
        temperature=temperature,
        timeout_sec=timeout_sec,
    )



def parse_role_routing_from_env(default_timeout_sec: int = 60, default_temperature: float = 0.0) -> dict[str, RoleRouting]:
    defaults = {
        "architect": "openai:gpt-4.1,openai:gpt-4.1-mini",
        "implementer": "openai:gpt-4.1,openai:gpt-4.1-mini",
        "reviewer": "openai:gpt-4.1-mini,openai:gpt-4o-mini",
        "validator": "openai:gpt-4.1-mini,openai:gpt-4o-mini",
    }

    routing: dict[str, RoleRouting] = {}
    for role in ROLES:
        env_key = f"{role.upper()}_MODEL_CHAIN"
        raw = os.getenv(env_key, defaults[role])
        parsed_chain = tuple(
            _parse_route_item(item, default_timeout_sec=default_timeout_sec, default_temperature=default_temperature)
            for item in raw.split(",")
            if item.strip()
        )
        if not parsed_chain:
            raise ValueError(f"{env_key} must contain at least one model")
        routing[role] = RoleRouting(primary=parsed_chain[0], fallbacks=parsed_chain[1:])

    return routing



def default_role_routing() -> dict[str, RoleRouting]:
    return parse_role_routing_from_env()
