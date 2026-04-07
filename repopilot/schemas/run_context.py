from __future__ import annotations

from dataclasses import dataclass, field

from repopilot.schemas.enums import RunState
from repopilot.schemas.contract import ContractReport
from repopilot.schemas.impact import ImpactReport
from repopilot.schemas.repo_map import RepoMap
from repopilot.schemas.task import TaskInput, TaskSpec
from repopilot.schemas.tool import ToolResult


@dataclass
class RunContext:
    run_id: str
    task_input: TaskInput
    state: RunState = RunState.INIT
    task_spec: TaskSpec | None = None
    repo_map: RepoMap | None = None
    contract_report: ContractReport | None = None
    impact_report: ImpactReport | None = None
    plan_steps: list[str] = field(default_factory=list)
    tool_results: list[ToolResult] = field(default_factory=list)
    failure_reason: str | None = None
    log_path: str | None = None
