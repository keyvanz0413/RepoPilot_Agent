from repopilot.core.recovery_manager import RecoveryManager
from repopilot.schemas.contract import ContractReport, FunctionContract
from repopilot.schemas.edit import EditResult
from repopilot.schemas.plan import ExecutionPlan
from repopilot.schemas.review import ReviewReport
from repopilot.schemas.run_context import RunContext
from repopilot.schemas.task import TaskInput


def _ctx() -> RunContext:
    return RunContext(
        run_id="test-run",
        task_input=TaskInput(raw_text="fix foo", repo_root="."),
        available_executors=["builtin"],
    )


def test_recovery_rolls_back_and_replans_after_failed_review_with_changes() -> None:
    ctx = _ctx()
    ctx.execution_plan = ExecutionPlan(goal="fix foo", requires_edit=True, executor_choice="builtin_code")
    ctx.edit_result = EditResult(
        applied=True,
        changed_files=["repopilot/app/state_machine.py"],
        summary="Applied builtin patch",
        original_contents={"repopilot/app/state_machine.py": "original"},
    )
    ctx.review_report = ReviewReport(decision="revise", findings=["Validation command failed"])

    action = RecoveryManager().run(ctx)

    assert action.action == "rollback_and_replan"
    assert action.next_state == "PLAN"
    assert action.rollback_files == ["repopilot/app/state_machine.py"]
    assert action.replan_required is True


def test_recovery_retries_retryable_codex_failure_once() -> None:
    ctx = _ctx()
    ctx.available_executors.append("codex")
    ctx.execution_plan = ExecutionPlan(goal="fix foo", requires_edit=True, executor_choice="codex")
    ctx.edit_result = EditResult(
        applied=False,
        changed_files=[],
        summary="Codex executor failed before applying edits.",
        executor="codex",
    )
    ctx.review_report = ReviewReport(decision="revise", findings=[ctx.edit_result.summary])

    action = RecoveryManager().run(ctx)

    assert action.action == "retry"
    assert action.next_state == "ACT"
    assert action.next_executor is None


def test_recovery_switches_to_builtin_when_codex_fails_and_function_contract_exists() -> None:
    ctx = _ctx()
    ctx.execution_plan = ExecutionPlan(goal="fix foo", requires_edit=True, executor_choice="codex")
    ctx.contract_report = ContractReport(
        target="fix foo",
        matched_files=["repopilot/app/state_machine.py"],
        function_contracts=[
            FunctionContract(
                path="repopilot/app/state_machine.py",
                symbol="next_state",
                parameters=["current"],
            )
        ],
    )
    ctx.edit_result = EditResult(
        applied=False,
        changed_files=[],
        summary="Plan selected the Codex executor, but no Codex executor is configured.",
        executor="codex",
    )
    ctx.review_report = ReviewReport(decision="revise", findings=[ctx.edit_result.summary])

    action = RecoveryManager().run(ctx)

    assert action.action == "switch_executor"
    assert action.next_state == "ACT"
    assert action.next_executor == "builtin_code"
