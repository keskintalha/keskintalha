from __future__ import annotations

import json
from dataclasses import dataclass
from textwrap import dedent

from langchain_core.messages import HumanMessage

from .config import AgentSettings
from .llm_registry import ChatModelFactory
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
    def __init__(self, settings: AgentSettings):
        self.settings = settings
        self.tools = build_tools(settings.workspace, settings.command_timeout_sec)
        self.model_factory = ChatModelFactory(settings)

    def _invoke_role(self, role: str, user_input: str) -> str:
        output = self.model_factory.invoke_role(
            role=role,
            prompt=ROLE_PROMPTS[role],
            tools=self.tools,
            messages=[HumanMessage(content=user_input)],
        )
        return output["messages"][-1].content

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

    def _run_reviewer_and_validator(self, task: str, architect_plan: str, implementation_log: str) -> tuple[str, str, ValidationResult]:
        reviewer_input = (
            "Review the implemented changes. Use tools to inspect edited files if needed.\n\n"
            f"Task: {task}\n\nPlan:\n{architect_plan}\n\nImplementation summary:\n{implementation_log}"
        )
        review_report = self._invoke_role("reviewer", reviewer_input)

        validator_input = (
            "Validate the final result and run relevant checks with tools.\n\n"
            f"Task: {task}\n\nPlan:\n{architect_plan}\n\nImplementation:\n{implementation_log}\n\n"
            f"Review:\n{review_report}"
        )
        validation_report = self._invoke_role("validator", validator_input)
        validation_result = self._parse_validation_result(validation_report)

        return review_report, validation_report, validation_result

    def run(self, task: str) -> AgentResult:
        architect_plan = self._invoke_role("architect", task)

        implementer_input = (
            f"User request:\n{task}\n\nArchitecture plan:\n{architect_plan}\n"
            "Now implement it using the provided tools."
        )
        implementation_log = self._invoke_role("implementer", implementer_input)

        review_report, validation_report, validation_result = self._run_reviewer_and_validator(
            task=task,
            architect_plan=architect_plan,
            implementation_log=implementation_log,
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
            review_report, validation_report, validation_result = self._run_reviewer_and_validator(
                task=task,
                architect_plan=architect_plan,
                implementation_log=implementation_log,
            )

        gate_result = self._evaluate_gate(validation_result)

        return AgentResult(
            architect_plan=architect_plan,
            implementation_log=implementation_log,
            review_report=review_report,
            validation_report=validation_report,
            validation_result=validation_result,
            gate_result=gate_result,
            repair_cycles_used=repair_cycles_used,
        )
