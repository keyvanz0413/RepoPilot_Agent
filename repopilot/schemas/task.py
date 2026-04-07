from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

TaskType = Literal["bug_fix", "add_feature", "add_test", "refactor", "explain_repo"]


@dataclass
class TaskInput:
    raw_text: str
    repo_root: str
    test_command: str | None = None


@dataclass
class TaskSpec:
    task_type: TaskType
    target: str
    intent: str
    constraints: list[str] = field(default_factory=list)
