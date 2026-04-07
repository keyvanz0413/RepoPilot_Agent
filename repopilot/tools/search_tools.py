from __future__ import annotations

import subprocess
from pathlib import Path


class SearchTools:
    def __init__(self, repo_root: str) -> None:
        self.repo_root = Path(repo_root).resolve()

    def search_text(self, query: str) -> dict:
        command = ["rg", "-n", query, str(self.repo_root)]
        result = subprocess.run(command, capture_output=True, text=True, check=False)
        return {
            "query": query,
            "exit_code": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
        }
