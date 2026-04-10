from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class PlanStep:
    title: str
    description: str
    files_involved: list[str] = field(default_factory=list)


@dataclass
class ExecutionPlan:
    goal: str
    plan_kind: str = "code_edit"
    requires_edit: bool = True
    executor_choice: str = "builtin"
    steps: list[PlanStep] = field(default_factory=list)
    files_to_edit: list[str] = field(default_factory=list)
    edit_scope_reason: str = ""
    tests_to_run: list[str] = field(default_factory=list)
    success_criteria: list[str] = field(default_factory=list)
    approval_required: bool = False
    risk_level: str = "low"
    summary: str = ""
