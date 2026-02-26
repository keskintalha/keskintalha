from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(slots=True)
class AgentSettings:
    """Runtime configuration for the C++ agent."""

    workspace: Path
    architect_model: str = "gpt-4.1"
    implementer_model: str = "gpt-4.1"
    reviewer_model: str = "gpt-4.1-mini"
    validator_model: str = "gpt-4.1-mini"
    command_timeout_sec: int = 120

    def __post_init__(self) -> None:
        self.workspace = self.workspace.expanduser().resolve()
        if not self.workspace.exists() or not self.workspace.is_dir():
            raise ValueError(f"Workspace does not exist or is not a directory: {self.workspace}")
        if not (1 <= self.command_timeout_sec <= 900):
            raise ValueError("command_timeout_sec must be between 1 and 900")

    @property
    def models(self) -> dict[str, str]:
        return {
            "architect": self.architect_model,
            "implementer": self.implementer_model,
            "reviewer": self.reviewer_model,
            "validator": self.validator_model,
        }
