from __future__ import annotations

from dataclasses import dataclass
from textwrap import dedent

from langchain_core.messages import HumanMessage
from langchain_openai import ChatOpenAI
from langgraph.prebuilt import create_react_agent

from .config import AgentSettings
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

    def _build_agent(self, role: str):
        llm = ChatOpenAI(model=self.settings.models[role], temperature=0)
        return create_react_agent(model=llm, tools=self.tools, prompt=ROLE_PROMPTS[role])

    def run(self, task: str) -> AgentResult:
        architect = self._build_agent("architect")
        architect_out = architect.invoke({"messages": [HumanMessage(content=task)]})
        architect_plan = architect_out["messages"][-1].content

        implementer = self._build_agent("implementer")
        implementer_input = (
            f"User request:\n{task}\n\nArchitecture plan:\n{architect_plan}\n"
            "Now implement it using the provided tools."
        )
        implementer_out = implementer.invoke({"messages": [HumanMessage(content=implementer_input)]})
        implementation_log = implementer_out["messages"][-1].content

        reviewer = self._build_agent("reviewer")
        reviewer_input = (
            "Review the implemented changes. Use tools to inspect edited files if needed.\n\n"
            f"Task: {task}\n\nPlan:\n{architect_plan}\n\nImplementation summary:\n{implementation_log}"
        )
        reviewer_out = reviewer.invoke({"messages": [HumanMessage(content=reviewer_input)]})
        review_report = reviewer_out["messages"][-1].content

        validator = self._build_agent("validator")
        validator_input = (
            "Validate the final result and run relevant checks with tools.\n\n"
            f"Task: {task}\n\nPlan:\n{architect_plan}\n\nImplementation:\n{implementation_log}\n\n"
            f"Review:\n{review_report}"
        )
        validator_out = validator.invoke({"messages": [HumanMessage(content=validator_input)]})
        validation_report = validator_out["messages"][-1].content

        return AgentResult(
            architect_plan=architect_plan,
            implementation_log=implementation_log,
            review_report=review_report,
            validation_report=validation_report,
        )
