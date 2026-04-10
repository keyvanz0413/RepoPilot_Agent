from __future__ import annotations

from repopilot.schemas.review import ReviewReport
from repopilot.schemas.run_context import RunContext


class Reviewer:
    def run(self, ctx: RunContext) -> ReviewReport:
        if ctx.edit_result is None:
            return ReviewReport(decision="fail", findings=["Missing edit result"], summary="Review failed.")

        if ctx.execution_plan and not ctx.execution_plan.requires_edit:
            return ReviewReport(
                decision="pass",
                findings=[],
                summary="Analysis-only plan completed without repository edits.",
            )

        findings: list[str] = []
        if not ctx.edit_result.applied:
            findings.append(ctx.edit_result.summary)
        elif ctx.execution_plan and ctx.execution_plan.files_to_edit:
            allowed = set(ctx.execution_plan.files_to_edit)
            changed = set(ctx.edit_result.changed_files)
            outside = sorted(path for path in changed if path not in allowed)
            if outside:
                findings.append(f"Edited files outside approved scope: {', '.join(outside)}")

        expected_tests = []
        if ctx.execution_plan and ctx.execution_plan.tests_to_run:
            expected_tests = ctx.execution_plan.tests_to_run
        elif ctx.task_input.test_command:
            expected_tests = [ctx.task_input.test_command]

        if expected_tests:
            test_tool = next((item for item in reversed(ctx.tool_results) if item.tool_name == "run_test"), None)
            if test_tool is None:
                findings.append("Expected test execution result is missing")
            elif test_tool.data.get("exit_code") != 0:
                findings.append("Validation command failed")

        if ctx.execution_plan and ctx.execution_plan.success_criteria and not findings:
            if (
                ctx.execution_plan.requires_edit
                and not ctx.edit_result.changed_files
                and not self._is_noop_success(ctx.edit_result.summary)
            ):
                findings.append("Plan required repository edits, but no files were changed")

        if findings:
            return ReviewReport(decision="revise", findings=findings, summary="Further action is required.")
        return ReviewReport(decision="pass", findings=[], summary="Edit and validation look acceptable.")

    def _is_noop_success(self, summary: str) -> bool:
        lowered = summary.lower()
        return "already contains" in lowered or "already contain" in lowered or "already" in lowered
