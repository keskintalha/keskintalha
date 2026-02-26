from pathlib import Path

import pytest

from senior_cpp_agent.config import AgentSettings, ROLES, parse_role_routing_from_env


def test_parse_role_routing_from_env_defaults(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("ARCHITECT_MODEL_CHAIN", raising=False)
    routing = parse_role_routing_from_env()
    assert set(routing.keys()) == set(ROLES)
    assert routing["architect"].primary.provider == "openai"
    assert routing["architect"].fallbacks


def test_parse_role_routing_from_env_custom_with_fallback(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("ARCHITECT_MODEL_CHAIN", "openai:gpt-main@0.2:30,openai:gpt-fallback@0.0:45")
    routing = parse_role_routing_from_env(default_timeout_sec=60)
    chain = routing["architect"].chain
    assert chain[0].model == "gpt-main"
    assert chain[0].temperature == 0.2
    assert chain[0].timeout_sec == 30
    assert chain[1].model == "gpt-fallback"
    assert chain[1].timeout_sec == 45


def test_agent_settings_requires_provider_api_key(tmp_path: Path):
    with pytest.raises(ValueError, match="OPENAI_API_KEY"):
        AgentSettings(workspace=tmp_path)


def test_agent_settings_accepts_valid_provider_env(tmp_path: Path):
    settings = AgentSettings(workspace=tmp_path, openai_api_key="test-key")
    assert settings.role_routing["implementer"].primary.model
