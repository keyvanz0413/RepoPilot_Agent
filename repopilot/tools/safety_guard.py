from __future__ import annotations

import shlex
from pathlib import Path


class SafetyError(RuntimeError):
    pass


class SafetyGuard:
    ALLOWED_COMMAND_PREFIXES = {
        ("pytest",),
        ("python", "-m", "pytest"),
        ("python3", "-m", "pytest"),
    }

    def __init__(self, repo_root: str) -> None:
        self.repo_root = Path(repo_root).resolve()

    def ensure_path_allowed(self, path: str) -> Path:
        resolved = Path(path).resolve()
        try:
            resolved.relative_to(self.repo_root)
        except ValueError as exc:
            raise SafetyError(f"Path outside repo root is blocked: {resolved}") from exc
        return resolved

    def ensure_command_allowed(self, command: str) -> None:
        parts = tuple(shlex.split(command))
        if not parts:
            raise SafetyError("Empty command is blocked")
        if any(token in {"rm", "sudo"} for token in parts):
            raise SafetyError(f"Dangerous command is blocked: {command}")
        if parts[:1] == ("npm",):
            if parts[:2] != ("npm", "test"):
                raise SafetyError(f"Only npm test is allowed: {command}")
            return
        if not any(parts[: len(prefix)] == prefix for prefix in self.ALLOWED_COMMAND_PREFIXES):
            raise SafetyError(f"Command not allowed by safety guard: {command}")
