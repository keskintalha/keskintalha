from pathlib import Path

import pytest

from senior_cpp_agent.config import AgentSettings, ModelRoute, RoleRouting
from senior_cpp_agent.llm_registry import ChatModelFactory, ModelInvocationError


class DummyAgent:
    def __init__(self, should_fail: bool):
        self.should_fail = should_fail

    def invoke(self, _: dict):
        if self.should_fail:
            raise RuntimeError("boom")
        return {"messages": [{"content": "ok"}]}


def test_invoke_role_uses_fallback(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    settings = AgentSettings(
        workspace=tmp_path,
        openai_api_key="x",
        llm_retry_attempts=0,
        role_routing={
            "architect": RoleRouting(
                primary=ModelRoute(provider="openai", model="primary"),
                fallbacks=(ModelRoute(provider="openai", model="fallback"),),
            ),
            "implementer": RoleRouting(primary=ModelRoute(provider="openai", model="i")),
            "reviewer": RoleRouting(primary=ModelRoute(provider="openai", model="r")),
            "validator": RoleRouting(primary=ModelRoute(provider="openai", model="v")),
        },
    )
    factory = ChatModelFactory(settings)

    models_seen: list[str] = []

    def fake_create_agent(route: ModelRoute, tools, prompt):
        models_seen.append(route.model)
        return DummyAgent(should_fail=route.model == "primary")

    monkeypatch.setattr(factory, "_create_agent", fake_create_agent)

    result = factory.invoke_role(role="architect", prompt="p", tools=[], messages=[])
    assert result["messages"][-1]["content"] == "ok"
    assert models_seen == ["primary", "fallback"]


def test_invoke_role_raises_after_retries(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    settings = AgentSettings(workspace=tmp_path, openai_api_key="x", llm_retry_attempts=1)
    factory = ChatModelFactory(settings)

    monkeypatch.setattr(factory, "_create_agent", lambda route, tools, prompt: DummyAgent(should_fail=True))

    with pytest.raises(ModelInvocationError, match="All model routes failed"):
        factory.invoke_role(role="architect", prompt="p", tools=[], messages=[])
