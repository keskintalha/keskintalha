from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
import subprocess


@dataclass(frozen=True, slots=True)
class CppProfile:
    name: str
    build_type: str
    sanitizer: str | None = None


@dataclass(frozen=True, slots=True)
class PipelineStepResult:
    name: str
    status: str
    duration_sec: float
    key_output: str
    artifacts: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class CppPipelineResult:
    profile: str
    steps: tuple[PipelineStepResult, ...]

    @property
    def passed(self) -> bool:
        return all(step.status == "passed" for step in self.steps)

    def to_dict(self) -> dict[str, object]:
        return {
            "profile": self.profile,
            "passed": self.passed,
            "steps": [
                {
                    "name": step.name,
                    "status": step.status,
                    "duration_sec": round(step.duration_sec, 3),
                    "key_output": step.key_output,
                    "artifacts": list(step.artifacts),
                }
                for step in self.steps
            ],
        }


DEFAULT_CPP_PROFILES: dict[str, CppProfile] = {
    "debug": CppProfile(name="debug", build_type="Debug"),
    "release": CppProfile(name="release", build_type="Release"),
    "asan": CppProfile(name="asan", build_type="Debug", sanitizer="address"),
    "ubsan": CppProfile(name="ubsan", build_type="Debug", sanitizer="undefined"),
}


class CppPipeline:
    def __init__(
        self,
        workspace: Path,
        timeout_sec: int,
        profiles: dict[str, CppProfile] | None = None,
        command_runner=None,
    ):
        self.workspace = workspace
        self.timeout_sec = timeout_sec
        self.profiles = profiles or DEFAULT_CPP_PROFILES
        self.command_runner = command_runner or self._run_command

    def _run_command(self, command: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            command,
            cwd=self.workspace,
            shell=True,
            text=True,
            timeout=self.timeout_sec,
            capture_output=True,
            check=False,
        )

    @staticmethod
    def _extract_key_output(result: subprocess.CompletedProcess[str]) -> str:
        for chunk in (result.stdout.strip(), result.stderr.strip()):
            if chunk:
                return "\n".join(chunk.splitlines()[:8])
        return "(no output)"

    def _build_step(self, name: str, command: str, artifacts: tuple[str, ...] = ()) -> PipelineStepResult:
        started = time.perf_counter()
        result = self.command_runner(command)
        duration = time.perf_counter() - started
        status = "passed" if result.returncode == 0 else "failed"
        return PipelineStepResult(
            name=name,
            status=status,
            duration_sec=duration,
            key_output=self._extract_key_output(result),
            artifacts=artifacts,
        )

    def run(self, profile_name: str) -> CppPipelineResult:
        if profile_name not in self.profiles:
            raise ValueError(f"Unknown C++ profile: {profile_name}")
        profile = self.profiles[profile_name]

        build_dir = self.workspace / "build" / profile.name
        build_dir.mkdir(parents=True, exist_ok=True)

        configure_flags = [f"-DCMAKE_BUILD_TYPE={profile.build_type}"]
        if profile.sanitizer:
            sanitizer_flag = f"-fsanitize={profile.sanitizer}"
            configure_flags.extend(
                [
                    f"-DCMAKE_CXX_FLAGS={sanitizer_flag}",
                    f"-DCMAKE_C_FLAGS={sanitizer_flag}",
                    "-DCMAKE_EXE_LINKER_FLAGS=-fsanitize=%s" % profile.sanitizer,
                ]
            )

        steps: list[PipelineStepResult] = []
        configure_cmd = f"cmake -S . -B {build_dir} {' '.join(configure_flags)}"
        steps.append(self._build_step("configure", configure_cmd, artifacts=(str(build_dir),)))

        if steps[-1].status == "passed":
            steps.append(self._build_step("build", f"cmake --build {build_dir}", artifacts=(str(build_dir),)))

        if steps[-1].status == "passed":
            steps.append(self._build_step("test", f"ctest --test-dir {build_dir} --output-on-failure"))

        if steps[-1].status == "passed":
            steps.append(
                self._build_step(
                    "lint",
                    f"cmake --build {build_dir} --target clang-tidy",
                    artifacts=(str(build_dir / 'compile_commands.json'),),
                )
            )

        if profile.sanitizer and steps[-1].status == "passed":
            steps.append(
                self._build_step(
                    "sanitizer",
                    f"ctest --test-dir {build_dir} --output-on-failure",
                )
            )

        return CppPipelineResult(profile=profile.name, steps=tuple(steps))


__all__ = [
    "CppPipeline",
    "CppPipelineResult",
    "PipelineStepResult",
    "CppProfile",
    "DEFAULT_CPP_PROFILES",
]
