from __future__ import annotations

import subprocess

from repopilot.tools.safety_guard import SafetyGuard


class TestRunner:
    def run_test(self, command: str) -> dict:
        guard = SafetyGuard(".")
        guard.ensure_command_allowed(command)
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            check=False,
        )
        return {
            "command": command,
            "exit_code": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
        }
