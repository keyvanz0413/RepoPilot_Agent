from __future__ import annotations

import subprocess

from repopilot.tools.safety_guard import SafetyGuard


class TestRunner:
    def __init__(self, repo_root: str) -> None:
        self.repo_root = repo_root

    def run_test(self, command: str) -> dict:
        guard = SafetyGuard(self.repo_root)
        guard.ensure_command_allowed(command)
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            check=False,
            cwd=self.repo_root,
        )
        return {
            "command": command,
            "exit_code": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
        }
