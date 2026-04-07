from __future__ import annotations

import subprocess
from pathlib import Path


class GitTools:
    def __init__(self, repo_root: str) -> None:
        self.repo_root = Path(repo_root).resolve()

    def create_checkpoint(self) -> dict:
        check = subprocess.run(
            ["git", "rev-parse", "--is-inside-work-tree"],
            cwd=self.repo_root,
            capture_output=True,
            text=True,
            check=False,
        )
        if check.returncode != 0:
            return {
                "created": False,
                "checkpoint_ref": None,
                "message": "Not a git repository",
            }

        result = subprocess.run(
            ["git", "stash", "create", "repopilot-checkpoint"],
            cwd=self.repo_root,
            capture_output=True,
            text=True,
            check=False,
        )
        checkpoint_ref = result.stdout.strip() or None
        return {
            "created": checkpoint_ref is not None,
            "checkpoint_ref": checkpoint_ref,
            "message": "Checkpoint captured" if checkpoint_ref else "No checkpoint created",
        }

    def revert_checkpoint(self, checkpoint_ref: str | None) -> dict:
        if not checkpoint_ref:
            return {
                "reverted": False,
                "message": "No checkpoint ref available",
            }

        check = subprocess.run(
            ["git", "rev-parse", "--is-inside-work-tree"],
            cwd=self.repo_root,
            capture_output=True,
            text=True,
            check=False,
        )
        if check.returncode != 0:
            return {
                "reverted": False,
                "message": "Not a git repository",
            }

        result = subprocess.run(
            ["git", "diff", "--stat", checkpoint_ref, "HEAD"],
            cwd=self.repo_root,
            capture_output=True,
            text=True,
            check=False,
        )
        return {
            "reverted": False,
            "message": "Git checkpoint restore is not active yet; use file rollback path.",
            "diff_stat": result.stdout,
        }
