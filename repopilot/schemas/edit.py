from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class CodexReferenceSnippet:
    path: str
    line: int
    text: str


@dataclass
class ProposedFileEdit:
    path: str
    content: str
    rationale: str = ""


@dataclass
class CodexEditRequest:
    request_version: str
    repo_root: str
    goal: str
    task_type: str = ""
    allowed_files: list[str] = field(default_factory=list)
    required_tests: list[str] = field(default_factory=list)
    constraints: list[str] = field(default_factory=list)
    repo_instructions: list[str] = field(default_factory=list)
    editing_rules: list[str] = field(default_factory=list)
    testing_rules: list[str] = field(default_factory=list)
    plan_steps: list[str] = field(default_factory=list)
    retrieval_summary: str = ""
    contract_summary: str = ""
    impact_summary: str = ""
    plan_summary: str = ""
    target_symbol: str | None = None
    contract_files: list[str] = field(default_factory=list)
    impact_files: list[str] = field(default_factory=list)
    reference_snippets: list[CodexReferenceSnippet] = field(default_factory=list)


@dataclass
class EditResult:
    applied: bool
    changed_files: list[str] = field(default_factory=list)
    summary: str = ""
    errors: list[str] = field(default_factory=list)
    original_contents: dict[str, str] = field(default_factory=dict)
    executor: str = "builtin"
