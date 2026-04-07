from __future__ import annotations

from repopilot.schemas.review import ReviewReport
from repopilot.schemas.run_context import RunContext


class Reviewer:
    def run(self, ctx: RunContext) -> ReviewReport:
        if ctx.edit_result is None:
            return ReviewReport(decision="fail", findings=["Missing edit result"], summary="Review failed.")

        findings: list[str] = []
        if not ctx.edit_result.applied:
            findings.append(ctx.edit_result.summary)

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

        if findings:
            return ReviewReport(decision="revise", findings=findings, summary="Further action is required.")
        return ReviewReport(decision="pass", findings=[], summary="Edit and validation look acceptable.")
