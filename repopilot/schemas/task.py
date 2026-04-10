from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

TaskType = Literal[
    "bug_fix",
    "add_feature",
    "add_test",
    "refactor",
    "doc_update",
    "explain_repo",
    "explain_target",
]
ScopeHint = Literal["symbol", "file", "module", "repo", "unknown"]


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
    target_symbols: list[str] = field(default_factory=list)
    target_files: list[str] = field(default_factory=list)
    scope_hint: ScopeHint = "unknown"
    constraints: list[str] = field(default_factory=list)
