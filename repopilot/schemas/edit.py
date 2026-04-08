from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ProposedFileEdit:
    path: str
    content: str
    rationale: str = ""


@dataclass
class CodexEditRequest:
    goal: str
    allowed_files: list[str] = field(default_factory=list)
    task_type: str = ""
    constraints: list[str] = field(default_factory=list)
    retrieval_summary: str = ""
    contract_summary: str = ""
    impact_summary: str = ""
    plan_summary: str = ""
    supporting_context: list[str] = field(default_factory=list)


@dataclass
class EditResult:
    applied: bool
    changed_files: list[str] = field(default_factory=list)
    summary: str = ""
    errors: list[str] = field(default_factory=list)
    original_contents: dict[str, str] = field(default_factory=dict)
    executor: str = "builtin"
