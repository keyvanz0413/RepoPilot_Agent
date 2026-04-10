from __future__ import annotations

from pathlib import Path


class RepoInstructionLoader:
    DEFAULT_PATHS = [
        "CLAUDE.md",
        "AGENTS.md",
        ".repopilot/instructions.md",
        "README.md",
    ]

    def __init__(self, repo_root: str) -> None:
        self.repo_root = Path(repo_root).resolve()

    def load(self) -> list[str]:
        instructions: list[str] = []
        for rel_path in self.DEFAULT_PATHS:
            path = self.repo_root / rel_path
            if not path.exists() or not path.is_file():
                continue
            try:
                content = path.read_text(encoding="utf-8").strip()
            except OSError:
                continue
            if not content:
                continue
            excerpt = content[:1200]
            instructions.append(f"{rel_path}:\n{excerpt}")
        return instructions
