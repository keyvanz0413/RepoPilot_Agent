from __future__ import annotations

from dataclasses import dataclass, field

from repopilot.schemas.enums import RunState
from repopilot.schemas.contract import ContractReport
from repopilot.schemas.edit import EditResult
from repopilot.schemas.impact import ImpactReport
from repopilot.schemas.local_retrieval import LocalRetrievalReport
from repopilot.schemas.plan import ExecutionPlan
from repopilot.schemas.recovery import RecoveryAction
from repopilot.schemas.retrieval import RetrievalDecision
from repopilot.schemas.repo_map import RepoMap
from repopilot.schemas.review import ReviewReport
from repopilot.schemas.task import TaskInput, TaskSpec
from repopilot.schemas.tool import ToolResult


@dataclass
class RunContext:
    run_id: str
    task_input: TaskInput
    state: RunState = RunState.INIT
    task_spec: TaskSpec | None = None
    retrieval_decision: RetrievalDecision | None = None
    local_retrieval_report: LocalRetrievalReport | None = None
    repo_map: RepoMap | None = None
    contract_report: ContractReport | None = None
    impact_report: ImpactReport | None = None
    plan_steps: list[str] = field(default_factory=list)
    execution_plan: ExecutionPlan | None = None
    edit_result: EditResult | None = None
    review_report: ReviewReport | None = None
    recovery_action: RecoveryAction | None = None
    tool_results: list[ToolResult] = field(default_factory=list)
    checkpoint_ref: str | None = None
    retrieval_escalations: int = 0
    recovery_attempts: int = 0
    failure_reason: str | None = None
    log_path: str | None = None
