from __future__ import annotations

from repopilot.schemas.recovery import RecoveryAction
from repopilot.schemas.run_context import RunContext


class RecoveryManager:
    MAX_RECOVERY_ATTEMPTS = 2
    RETRYABLE_SUMMARY_SNIPPETS = (
        "codex executor failed before applying edits",
        "codex executor returned no file edits",
        "codex executor could not apply any proposed edits",
        "write_file failed",
    )

    def run(self, ctx: RunContext) -> RecoveryAction:
        if ctx.review_report is None or ctx.review_report.decision != "revise":
            return self._abort(ctx, "Recovery manager requires a failed review result before acting.")

        if ctx.recovery_attempts >= self.MAX_RECOVERY_ATTEMPTS:
            return self._abort(ctx, "Recovery budget was exhausted without finding a safe retry strategy.")

        if self._should_rollback_and_replan(ctx):
            return RecoveryAction(
                action="rollback_and_replan",
                next_state="PLAN",
                reason="Rollback applied before rebuilding the execution plan after a failed review.",
                rollback_files=list(ctx.edit_result.changed_files),
                replan_required=True,
            )

        if self._should_switch_to_builtin_code(ctx):
            return RecoveryAction(
                action="switch_executor",
                next_state="ACT",
                reason="Switch execution from Codex to builtin_code because a function contract is available.",
                next_executor="builtin_code",
            )

        if self._should_retry_executor(ctx):
            executor = ctx.execution_plan.executor_choice if ctx.execution_plan else "current executor"
            return RecoveryAction(
                action="retry",
                next_state="ACT",
                reason=f"Retry {executor} once after a transient edit failure.",
            )

        return self._abort(ctx, "Recovery manager had no safe retry strategy for the current failure.")

    def _should_rollback_and_replan(self, ctx: RunContext) -> bool:
        if (
            ctx.edit_result is None
            or not ctx.edit_result.applied
            or not ctx.edit_result.changed_files
            or ctx.recovery_attempts > 0
        ):
            return False
        return bool(ctx.review_report and ctx.review_report.findings)

    def _should_switch_to_builtin_code(self, ctx: RunContext) -> bool:
        if ctx.recovery_attempts > 0:
            return False
        if ctx.execution_plan is None or ctx.execution_plan.executor_choice != "codex":
            return False
        if ctx.edit_result is None or ctx.edit_result.applied:
            return False
        if ctx.contract_report is None or not ctx.contract_report.function_contracts:
            return False
        if "builtin" not in ctx.available_executors:
            return False

        lowered = ctx.edit_result.summary.lower()
        return "codex" in lowered

    def _should_retry_executor(self, ctx: RunContext) -> bool:
        if ctx.recovery_attempts > 0:
            return False
        if ctx.execution_plan is None or not ctx.execution_plan.requires_edit:
            return False
        if ctx.edit_result is None or ctx.edit_result.applied:
            return False
        if ctx.edit_result.changed_files:
            return False

        lowered = ctx.edit_result.summary.lower()
        return any(snippet in lowered for snippet in self.RETRYABLE_SUMMARY_SNIPPETS)

    def _abort(self, ctx: RunContext, reason: str) -> RecoveryAction:
        if ctx.edit_result and ctx.edit_result.applied and ctx.edit_result.changed_files:
            return RecoveryAction(
                action="rollback",
                next_state="FAILED",
                reason=reason,
                rollback_files=list(ctx.edit_result.changed_files),
            )
        return RecoveryAction(
            action="abort",
            next_state="FAILED",
            reason=reason,
        )
