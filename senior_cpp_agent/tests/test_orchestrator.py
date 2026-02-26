import importlib
import logging
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace


def _load_orchestrator_module():
    langchain_core = ModuleType("langchain_core")
    messages_module = ModuleType("langchain_core.messages")

    class HumanMessage:  # noqa: D401 - lightweight test shim
        def __init__(self, content: str):
            self.content = content

    messages_module.HumanMessage = HumanMessage
    langchain_core.messages = messages_module

    sys.modules.setdefault("langchain_core", langchain_core)
    sys.modules["langchain_core.messages"] = messages_module

    return importlib.import_module("senior_cpp_agent.orchestrator")


orchestrator_module = _load_orchestrator_module()
SeniorCppAgent = orchestrator_module.SeniorCppAgent


class StubInvoker:
    def __init__(self, responses_by_role: dict[str, list[str]]):
        self.responses_by_role = {role: list(items) for role, items in responses_by_role.items()}
        self.calls: list[tuple[str, str]] = []

    def __call__(self, role: str, user_input: str) -> str:
        self.calls.append((role, user_input))
        queue = self.responses_by_role[role]
        if not queue:
            raise AssertionError(f"No stub response left for role={role}")
        return queue.pop(0)


class StubPipeline:
    def __init__(self):
        self.calls: list[str] = []

    def run(self, profile: str):
        self.calls.append(profile)
        return SimpleNamespace(
            passed=True,
            steps=[SimpleNamespace(name="configure", status="passed")],
            to_dict=lambda: {"profile": profile, "passed": True, "steps": []},
        )


class StubRecorder:
    def __init__(self):
        self.run_dir = Path("/tmp/test-run")

    def write_json(self, name, payload):
        return name, payload

    def write_text(self, name, payload):
        return name, payload


class StubRuntime:
    def __init__(self):
        self.request_id = "req-1"
        self.run_id = "run-1"
        self.recorder = StubRecorder()
        self.decisions = []

    def logger(self):
        return logging.LoggerAdapter(logging.getLogger("test"), {"request_id": self.request_id, "run_id": self.run_id})

    def add_decision(self, *, stage: str, decision: str, success: bool):
        self.decisions.append((stage, decision, success))

    def artifacts_snapshot(self):
        return {"metrics": {"architect": {"calls": 1}}, "decisions": self.decisions}


def _make_agent(max_repair_cycles: int, invoker: StubInvoker) -> SeniorCppAgent:
    agent = SeniorCppAgent.__new__(SeniorCppAgent)
    agent.settings = SimpleNamespace(max_repair_cycles=max_repair_cycles)
    agent._invoke_role = invoker
    agent.pipeline = StubPipeline()
    agent.runtime = StubRuntime()
    agent.log = agent.runtime.logger()
    return agent


def test_orchestrator_gate_pass_without_repair():
    invoker = StubInvoker(
        {
            "architect": ["plan"],
            "implementer": ["implementation"],
            "reviewer": ["review"],
            "validator": ['{"passed": true, "failed_checks": [], "recommendations": []}'],
        }
    )
    agent = _make_agent(max_repair_cycles=0, invoker=invoker)

    result = agent.run("task")

    assert result.validation_result.passed is True
    assert result.gate_result.merge_ready is True
    assert result.gate_result.reasons == []
    assert result.repair_cycles_used == 0
    assert result.request_id == "req-1"


def test_orchestrator_gate_fail_on_build_and_tests():
    invoker = StubInvoker(
        {
            "architect": ["plan"],
            "implementer": ["implementation"],
            "reviewer": ["review"],
            "validator": [
                '{"passed": false, "failed_checks": ["build failed: linker error", "tests failed: ctest"], "recommendations": ["fix build", "fix tests"]}'
            ],
        }
    )
    agent = _make_agent(max_repair_cycles=0, invoker=invoker)

    result = agent.run("task")

    assert result.gate_result.merge_ready is False
    assert "Build checks failed." in result.gate_result.reasons
    assert "Test checks failed." in result.gate_result.reasons
    assert result.repair_cycles_used == 0


def test_orchestrator_repair_cycle_until_pass():
    invoker = StubInvoker(
        {
            "architect": ["plan"],
            "implementer": ["initial impl", "repaired impl"],
            "reviewer": ["review 1", "review 2"],
            "validator": [
                '{"passed": false, "failed_checks": ["test failed"], "recommendations": ["fix failing test"]}',
                '{"passed": true, "failed_checks": [], "recommendations": []}',
            ],
        }
    )
    agent = _make_agent(max_repair_cycles=1, invoker=invoker)

    result = agent.run("task")

    assert result.validation_result.passed is True
    assert result.repair_cycles_used == 1
    assert result.gate_result.merge_ready is True

    implementer_prompts = [prompt for role, prompt in invoker.calls if role == "implementer"]
    assert len(implementer_prompts) == 2
    assert "Failed checks" in implementer_prompts[1]
    assert "fix failing test" in implementer_prompts[1]


def test_orchestrator_uses_selected_pipeline_profile():
    invoker = StubInvoker(
        {
            "architect": ["plan"],
            "implementer": ["implementation"],
            "reviewer": ["review"],
            "validator": ['{"passed": true, "failed_checks": [], "recommendations": []}'],
        }
    )
    agent = _make_agent(max_repair_cycles=0, invoker=invoker)

    agent.run("task", profile="asan")

    assert agent.pipeline.calls == ["asan"]


def test_create_run_report_redacts_sensitive_data():
    agent = SeniorCppAgent.__new__(SeniorCppAgent)
    result = SimpleNamespace(
        request_id="req",
        run_id="run",
        run_dir="/tmp/run",
        architect_plan="plan",
        implementation_log="impl",
        review_report="review",
        validation_report="report",
        validation_result=SimpleNamespace(passed=True, failed_checks=[], recommendations=[]),
        pipeline_result=SimpleNamespace(to_dict=lambda: {"api_key": "secret"}),
        gate_result=SimpleNamespace(merge_ready=True, reasons=[]),
        repair_cycles_used=0,
        metrics={},
    )

    report = agent.create_run_report(result)

    assert report["pipeline_result"]["api_key"] == "[REDACTED]"
