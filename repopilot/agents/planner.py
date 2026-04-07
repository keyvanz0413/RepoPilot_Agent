from __future__ import annotations

import importlib.util

from repopilot.schemas.plan import ExecutionPlan, PlanStep
from repopilot.schemas.run_context import RunContext


class Planner:
    def run(self, ctx: RunContext) -> ExecutionPlan:
        steps: list[PlanStep] = [
            PlanStep(
                title="Inspect target",
                description="Use repo map and contract matches to narrow edit scope.",
                files_involved=ctx.contract_report.matched_files if ctx.contract_report else [],
            ),
            PlanStep(
                title="Validate impact",
                description="Review references and test files before editing.",
                files_involved=ctx.impact_report.affected_files if ctx.impact_report else [],
            ),
            PlanStep(
                title="Apply minimal patch",
                description="Only patch a supported Python function signature.",
                files_involved=ctx.contract_report.matched_files if ctx.contract_report else [],
            ),
        ]
        tests_to_run: list[str] = self._select_tests(ctx)
        return ExecutionPlan(
            goal=ctx.task_input.raw_text,
            steps=steps,
            files_to_edit=list(ctx.contract_report.matched_files) if ctx.contract_report else [],
            tests_to_run=tests_to_run,
            risk_level=ctx.impact_report.risk_level if ctx.impact_report else "medium",
            summary="Built a conservative execution plan from repo context.",
        )

    def _select_tests(self, ctx: RunContext) -> list[str]:
        if ctx.task_input.test_command:
            return [ctx.task_input.test_command]
        if (
            ctx.impact_report
            and ctx.impact_report.related_tests
            and importlib.util.find_spec("pytest") is not None
        ):
            joined = " ".join(ctx.impact_report.related_tests[:5])
            return [f"python3 -m pytest {joined}"]
        return []
