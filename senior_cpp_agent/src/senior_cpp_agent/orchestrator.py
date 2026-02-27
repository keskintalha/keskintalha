from __future__ import annotations

import json
from dataclasses import dataclass
from textwrap import dedent
from typing import Any, cast

from langchain_core.messages import HumanMessage

from .config import AgentSettings
from .cpp_pipeline import CppPipeline, CppPipelineResult
from .llm_registry import ChatModelFactory
from .runtime import RuntimeContext, sanitize_payload
from .tools import build_tools


@dataclass(frozen=True, slots=True)
class ValidationResult:
    passed: bool
    failed_checks: list[str]
    recommendations: list[str]


@dataclass(frozen=True, slots=True)
class GateResult:
    merge_ready: bool
    reasons: list[str]


@dataclass
class AgentResult:
    architect_plan: str
    implementation_log: str
    review_report: str
    validation_report: str
    validation_result: ValidationResult
    gate_result: GateResult
    repair_cycles_used: int
    pipeline_result: CppPipelineResult
    request_id: str
    run_id: str
    run_dir: str
    metrics: dict


ROLE_PROMPTS = {
    "architect": dedent(
        """
        You are a Principal C++ Software Architect.
        Produce a concise but actionable implementation plan for the user's request.
        Focus on C++17/20 best practices, testability, and production-readiness.
        """
    ).strip(),
    "implementer": dedent(
        """
        You are a Senior C++ Developer.
        Apply the architecture plan using available file and command tools.
        Keep changes minimal, robust, and maintainable.
        """
    ).strip(),
    "reviewer": dedent(
        """
        You are a C++ Code Reviewer.
        Critically review resulting code for correctness, performance, style, and safety.
        Provide explicit risks and suggested fixes.
        """
    ).strip(),
    "validator": dedent(
        """
        You are a QA/Validation Engineer.
        Define and run validation steps with available tools.
        Return STRICT JSON with schema:
        {
          "passed": boolean,
          "failed_checks": ["..."] ,
          "recommendations": ["..."]
        }
        `failed_checks` MUST explicitly include failed build/test checks when applicable.
        `recommendations` should contain concrete repair guidance.
        """
    ).strip(),
}


class SeniorCppAgent:
    def __init__(self, settings: AgentSettings, runtime: RuntimeContext | None = None):
        self.settings = settings
        self.runtime = runtime or RuntimeContext(workspace=settings.workspace)
        self.log = self.runtime.logger()
        self.tools = build_tools(settings.workspace, settings.command_timeout_sec)
        self.model_factory = ChatModelFactory(settings, runtime=self.runtime)
        self.pipeline = CppPipeline(settings.workspace, settings.command_timeout_sec, profiles=settings.cpp_profiles)

    def _invoke_role(self, role: str, user_input: str) -> str:
        self.runtime.recorder.write_text(f"{role}_prompt.txt", user_input)
        self.log.info("Invoking role", extra={"event": "role_start", "role": role})
        output = self.model_factory.invoke_role(
            role=role,
            prompt=ROLE_PROMPTS[role],
            tools=self.tools,
            messages=[HumanMessage(content=user_input)],
        )
        content = output["messages"][-1].content
        self.runtime.recorder.write_text(f"{role}_decision.txt", str(content))
        self.runtime.add_decision(stage=role, decision=str(content)[:300], success=True)
        self.log.info("Role completed", extra={"event": "role_complete", "role": role})
        return str(content)

    def _parse_validation_result(self, validator_output: str) -> ValidationResult:
        try:
            raw = json.loads(validator_output)
        except json.JSONDecodeError:
            return ValidationResult(
                passed=False,
                failed_checks=["validator_output_not_json"],
                recommendations=["Return valid JSON with passed/failed_checks/recommendations."],
            )

        passed = bool(raw.get("passed", False))
        failed_checks = [str(item) for item in raw.get("failed_checks", []) if str(item).strip()]
        recommendations = [str(item) for item in raw.get("recommendations", []) if str(item).strip()]

        if passed and failed_checks:
            passed = False
            recommendations = [
                *recommendations,
                "Fix contradictory validator output: `passed=true` cannot contain failed_checks.",
            ]

        return ValidationResult(passed=passed, failed_checks=failed_checks, recommendations=recommendations)

    def _evaluate_gate(self, validation_result: ValidationResult) -> GateResult:
        reasons: list[str] = []
        if not validation_result.passed:
            reasons.append("Validator did not approve the result.")

        lowered_checks = [check.lower() for check in validation_result.failed_checks]
        if any("build" in check for check in lowered_checks):
            reasons.append("Build checks failed.")
        if any("test" in check for check in lowered_checks):
            reasons.append("Test checks failed.")

        if validation_result.failed_checks:
            reasons.append("Remaining failed checks exist.")

        return GateResult(merge_ready=not reasons, reasons=reasons)

    def _run_reviewer_and_validator(self, task: str, architect_plan: str, implementation_log: str, pipeline_result: CppPipelineResult) -> tuple[str, str, ValidationResult]:
        reviewer_input = (
            "Review the implemented changes. Use tools to inspect edited files if needed.\n\n"
            f"Task: {task}\n\nPlan:\n{architect_plan}\n\nImplementation summary:\n{implementation_log}"
        )
        review_report = self._invoke_role("reviewer", reviewer_input)

        validator_input = (
            "Validate the final result and run relevant checks with tools.\n\n"
            f"Task: {task}\n\nPlan:\n{architect_plan}\n\nImplementation:\n{implementation_log}\n\n"
            f"Review:\n{review_report}\n\n"
            "Use these real C++ pipeline results as primary evidence:\n"
            f"{json.dumps(pipeline_result.to_dict(), indent=2)}"
        )
        validation_report = self._invoke_role("validator", validator_input)
        validation_result = self._parse_validation_result(validation_report)

        if not pipeline_result.passed:
            failed_step_names = [step.name for step in pipeline_result.steps if step.status != "passed"]
            pipeline_checks = [f"pipeline step failed: {name}" for name in failed_step_names]
            failed_checks = list(dict.fromkeys([*validation_result.failed_checks, *pipeline_checks]))
            recommendations = list(validation_result.recommendations)
            recommendations.append("Fix failing C++ pipeline steps before merge.")
            validation_result = ValidationResult(
                passed=False,
                failed_checks=failed_checks,
                recommendations=list(dict.fromkeys(recommendations)),
            )

        return review_report, validation_report, validation_result

    def create_run_report(self, result: AgentResult) -> dict[str, Any]:
        return cast(dict[str, Any], sanitize_payload(
            {
                "request_id": result.request_id,
                "run_id": result.run_id,
                "run_dir": result.run_dir,
                "architect_plan": result.architect_plan,
                "implementation_log": result.implementation_log,
                "review_report": result.review_report,
                "validation_report": result.validation_report,
                "validation_result": {
                    "passed": result.validation_result.passed,
                    "failed_checks": result.validation_result.failed_checks,
                    "recommendations": result.validation_result.recommendations,
                },
                "pipeline_result": result.pipeline_result.to_dict(),
                "gate": {
                    "merge_ready": result.gate_result.merge_ready,
                    "reasons": result.gate_result.reasons,
                },
                "repair_cycles_used": result.repair_cycles_used,
                "metrics": result.metrics,
            }
        ))

    def run(self, task: str, profile: str = "debug") -> AgentResult:
        self.log.info("Starting run", extra={"event": "run_start", "profile": profile})
        architect_plan = self._invoke_role("architect", task)

        implementer_input = (
            f"User request:\n{task}\n\nArchitecture plan:\n{architect_plan}\n"
            "Now implement it using the provided tools."
        )
        implementation_log = self._invoke_role("implementer", implementer_input)

        pipeline_result = self.pipeline.run(profile)
        self.runtime.recorder.write_json("pipeline_result.json", sanitize_payload(pipeline_result.to_dict()))

        review_report, validation_report, validation_result = self._run_reviewer_and_validator(
            task=task,
            architect_plan=architect_plan,
            implementation_log=implementation_log,
            pipeline_result=pipeline_result,
        )

        repair_cycles_used = 0
        while not validation_result.passed and repair_cycles_used < self.settings.max_repair_cycles:
            repair_cycles_used += 1
            repair_input = (
                "Validator found actionable issues. Apply focused fixes.\n\n"
                f"Task: {task}\n\nArchitecture plan:\n{architect_plan}\n\n"
                f"Current implementation summary:\n{implementation_log}\n\n"
                f"Review report:\n{review_report}\n\n"
                f"Failed checks:\n- "
                + "\n- ".join(validation_result.failed_checks or ["(none provided)"])
                + "\n\nRecommendations:\n- "
                + "\n- ".join(validation_result.recommendations or ["(none provided)"])
            )
            implementation_log = self._invoke_role("implementer", repair_input)
            pipeline_result = self.pipeline.run(profile)
            self.runtime.recorder.write_json("pipeline_result.json", sanitize_payload(pipeline_result.to_dict()))
            review_report, validation_report, validation_result = self._run_reviewer_and_validator(
                task=task,
                architect_plan=architect_plan,
                implementation_log=implementation_log,
                pipeline_result=pipeline_result,
            )

        gate_result = self._evaluate_gate(validation_result)
        self.runtime.add_decision(stage="gate", decision="merge_ready" if gate_result.merge_ready else "blocked", success=gate_result.merge_ready)
        snapshot = self.runtime.artifacts_snapshot()
        self.runtime.recorder.write_json("run_summary.json", snapshot)
        self.log.info("Run completed", extra={"event": "run_complete", "merge_ready": gate_result.merge_ready})

        return AgentResult(
            architect_plan=architect_plan,
            implementation_log=implementation_log,
            review_report=review_report,
            validation_report=validation_report,
            validation_result=validation_result,
            gate_result=gate_result,
            repair_cycles_used=repair_cycles_used,
            pipeline_result=pipeline_result,
            request_id=self.runtime.request_id,
            run_id=self.runtime.run_id,
            run_dir=str(self.runtime.recorder.run_dir),
            metrics=snapshot["metrics"],
        )
