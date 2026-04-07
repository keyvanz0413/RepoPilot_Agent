from __future__ import annotations

from pathlib import Path

from repopilot.tools.safety_guard import SafetyGuard


class FileTools:
    def __init__(self, repo_root: str) -> None:
        self.safety_guard = SafetyGuard(repo_root)

    def read_file(self, path: str) -> dict:
        resolved = self.safety_guard.ensure_path_allowed(path)
        return {
            "path": str(resolved),
            "content": resolved.read_text(encoding="utf-8"),
        }

    def list_files(self, root: str | None = None) -> dict:
        base = self.safety_guard.ensure_path_allowed(root or str(self.safety_guard.repo_root))
        files = [str(path) for path in base.rglob("*") if path.is_file()]
        return {"root": str(base), "files": files}
