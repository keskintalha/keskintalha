from types import SimpleNamespace
from pathlib import Path

from senior_cpp_agent.cpp_pipeline import CppPipeline, DEFAULT_CPP_PROFILES
from senior_cpp_agent.tools import _is_command_allowed


class RecordingRunner:
    def __init__(self):
        self.commands: list[str] = []

    def __call__(self, command: str):
        self.commands.append(command)
        return SimpleNamespace(returncode=0, stdout="ok", stderr="")


def test_cpp_pipeline_command_assembly_for_asan(tmp_path: Path):
    runner = RecordingRunner()
    pipeline = CppPipeline(tmp_path, timeout_sec=10, command_runner=runner)

    result = pipeline.run("asan")

    assert result.profile == "asan"
    assert [step.name for step in result.steps] == ["configure", "build", "test", "lint", "sanitizer"]
    assert "-DCMAKE_BUILD_TYPE=Debug" in runner.commands[0]
    assert "-fsanitize=address" in runner.commands[0]
    assert runner.commands[3].startswith("cmake --build") and "clang-tidy" in runner.commands[3]


def test_cpp_pipeline_profiles_are_available():
    assert set(DEFAULT_CPP_PROFILES) == {"debug", "release", "asan", "ubsan"}


def test_pipeline_commands_follow_policy_prefixes(tmp_path: Path):
    runner = RecordingRunner()
    pipeline = CppPipeline(tmp_path, timeout_sec=10, command_runner=runner)

    pipeline.run("debug")

    for command in runner.commands:
        assert _is_command_allowed(command), f"not policy-compatible: {command}"
