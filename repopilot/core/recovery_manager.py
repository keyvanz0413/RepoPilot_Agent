from __future__ import annotations

from repopilot.schemas.recovery import RecoveryAction
from repopilot.schemas.run_context import RunContext


class RecoveryManager:
    def run(self, ctx: RunContext) -> RecoveryAction:
        if ctx.review_report and ctx.review_report.decision == "revise":
            return RecoveryAction(
                action="abort",
                next_state="FAILED",
                reason="Conservative recovery: stop after one failed review cycle.",
            )
        return RecoveryAction(
            action="abort",
            next_state="FAILED",
            reason="Recovery manager had no safe retry strategy for the current failure.",
        )
