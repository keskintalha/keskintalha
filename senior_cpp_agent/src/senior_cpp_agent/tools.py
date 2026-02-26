from __future__ import annotations

import subprocess
from pathlib import Path

SAFE_COMMAND_PREFIXES = {
    "cmake",
    "ctest",
    "make",
    "ninja",
    "gcc",
    "g++",
    "clang",
    "clang++",
    "pytest",
    "python",
}


def _is_command_allowed(command: str) -> bool:
    stripped = command.strip()
    if not stripped:
        return False
    first_token = stripped.split()[0]
    return first_token in SAFE_COMMAND_PREFIXES


def build_tools(workspace: Path, timeout_sec: int):
    from langchain_core.tools import tool

    @tool
    def read_file(relative_path: str) -> str:
        """Read a UTF-8 text file from the workspace and return its content."""
        target = (workspace / relative_path).resolve()
        if workspace not in target.parents and target != workspace:
            raise ValueError("Path escapes workspace")
        return target.read_text(encoding="utf-8")

    @tool
    def write_file(relative_path: str, content: str) -> str:
        """Write UTF-8 content to a file in the workspace."""
        target = (workspace / relative_path).resolve()
        if workspace not in target.parents and target != workspace:
            raise ValueError("Path escapes workspace")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return f"Wrote {relative_path}"

    @tool
    def run_command(command: str) -> str:
        """Run a safe build/test command in workspace (cmake/ctest/make/ninja/g++/clang++/pytest/python)."""
        if not _is_command_allowed(command):
            return (
                "Command rejected by policy. Allowed prefixes: "
                + ", ".join(sorted(SAFE_COMMAND_PREFIXES))
            )
        result = subprocess.run(
            command,
            cwd=workspace,
            shell=True,
            text=True,
            timeout=timeout_sec,
            capture_output=True,
            check=False,
        )
        return (
            f"exit_code={result.returncode}\n"
            f"stdout:\n{result.stdout}\n"
            f"stderr:\n{result.stderr}"
        )

    return [read_file, write_file, run_command]


__all__ = ["build_tools", "SAFE_COMMAND_PREFIXES", "_is_command_allowed"]
