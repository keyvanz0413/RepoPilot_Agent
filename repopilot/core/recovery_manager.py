from __future__ import annotations

from repopilot.schemas.recovery import RecoveryAction
from repopilot.schemas.run_context import RunContext


class RecoveryManager:
    def run(self, ctx: RunContext) -> RecoveryAction:
        if (
            ctx.review_report
            and ctx.review_report.decision == "revise"
            and ctx.edit_result
            and ctx.edit_result.applied
            and ctx.edit_result.changed_files
            and ctx.recovery_attempts == 0
        ):
            return RecoveryAction(
                action="rollback",
                next_state="FAILED",
                reason="Rollback applied after a failed review on the first recovery attempt.",
                rollback_files=list(ctx.edit_result.changed_files),
            )
        return RecoveryAction(
            action="abort",
            next_state="FAILED",
            reason="Recovery manager had no safe retry strategy for the current failure.",
        )
