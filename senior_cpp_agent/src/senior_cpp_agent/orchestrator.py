from __future__ import annotations

from dataclasses import dataclass
from textwrap import dedent

from langchain_core.messages import HumanMessage

from .config import AgentSettings
from .llm_registry import ChatModelFactory
from .tools import build_tools


@dataclass
class AgentResult:
    architect_plan: str
    implementation_log: str
    review_report: str
    validation_report: str


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
        Summarize whether solution is production-ready and what remains.
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

    def run(self, task: str) -> AgentResult:
        architect_plan = self._invoke_role("architect", task)

        implementer_input = (
            f"User request:\n{task}\n\nArchitecture plan:\n{architect_plan}\n"
            "Now implement it using the provided tools."
        )
        implementation_log = self._invoke_role("implementer", implementer_input)

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

        return AgentResult(
            architect_plan=architect_plan,
            implementation_log=implementation_log,
            review_report=review_report,
            validation_report=validation_report,
        )
