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
    steps: list[PlanStep] = field(default_factory=list)
    files_to_edit: list[str] = field(default_factory=list)
    tests_to_run: list[str] = field(default_factory=list)
    risk_level: str = "low"
    summary: str = ""
