from __future__ import annotations

from dataclasses import asdict
from pathlib import Path

from repopilot.agents.coder import Coder
from repopilot.agents.planner import Planner
from repopilot.agents.reviewer import Reviewer
from repopilot.app.logging import JsonlLogger
from repopilot.app.state_machine import TERMINAL_STATES, next_state
from repopilot.core.contract_validator import ContractValidator
from repopilot.core.impact_analyzer import ImpactAnalyzer
from repopilot.core.recovery_manager import RecoveryManager
from repopilot.core.repo_mapper import RepoMapper
from repopilot.schemas.enums import RunState
from repopilot.schemas.run_context import RunContext
from repopilot.schemas.task import TaskSpec
from repopilot.tools.tool_registry import ToolRegistry


class Orchestrator:
    def __init__(self, tool_registry: ToolRegistry, logger: JsonlLogger) -> None:
        self.tool_registry = tool_registry
        self.logger = logger
        self.repo_mapper = RepoMapper(".")
        self.contract_validator = ContractValidator(".")
        self.impact_analyzer = ImpactAnalyzer(".")
        self.planner = Planner()
        self.reviewer = Reviewer()
        self.recovery_manager = RecoveryManager()
        self.coder = Coder(tool_registry, ".")

    def run(self, ctx: RunContext) -> RunContext:
        self.repo_mapper = RepoMapper(ctx.task_input.repo_root)
        self.contract_validator = ContractValidator(ctx.task_input.repo_root)
        self.impact_analyzer = ImpactAnalyzer(ctx.task_input.repo_root)
        self.coder = Coder(self.tool_registry, ctx.task_input.repo_root)
        self._log(ctx, "run_started", {"repo_root": ctx.task_input.repo_root})

        while ctx.state not in TERMINAL_STATES:
            self._log(ctx, "state_enter", {"state": ctx.state})

            if ctx.state == RunState.INIT:
                ctx.state = next_state(ctx.state)
                continue

            if ctx.state == RunState.ANALYZE_TASK:
                ctx.task_spec = self._analyze_task(ctx)
                ctx.state = next_state(ctx.state)
                continue

            if ctx.state == RunState.MAP_REPO:
                ctx.repo_map = self.repo_mapper.run()
                self._log(ctx, "repo_mapped", asdict(ctx.repo_map))
                ctx.state = next_state(ctx.state)
                continue

            if ctx.state == RunState.VALIDATE_CONTRACT:
                if ctx.task_spec is None:
                    ctx.failure_reason = "Task spec missing before contract validation"
                    ctx.state = RunState.FAILED
                    continue
                ctx.contract_report = self.contract_validator.run(ctx.task_spec)
                self._log(ctx, "contract_validated", asdict(ctx.contract_report))
                ctx.state = next_state(ctx.state)
                continue

            if ctx.state == RunState.ANALYZE_IMPACT:
                if ctx.contract_report is None:
                    ctx.failure_reason = "Contract report missing before impact analysis"
                    ctx.state = RunState.FAILED
                    continue
                ctx.impact_report = self.impact_analyzer.run(ctx.contract_report)
                self._log(ctx, "impact_analyzed", asdict(ctx.impact_report))
                ctx.state = next_state(ctx.state)
                continue

            if ctx.state == RunState.PLAN:
                ctx.execution_plan = self.planner.run(ctx)
                self._log(ctx, "execution_plan_built", asdict(ctx.execution_plan))
                ctx.plan_steps = self._build_plan(ctx)
                ctx.state = next_state(ctx.state)
                continue

            if ctx.state == RunState.EDIT:
                checkpoint_result = self.tool_registry.run("create_checkpoint")
                ctx.tool_results.append(checkpoint_result)
                ctx.checkpoint_ref = checkpoint_result.data.get("checkpoint_ref")
                ctx.edit_result = self.coder.run(ctx)
                self._log(ctx, "edit_attempted", asdict(ctx.edit_result))
                ctx.state = next_state(ctx.state)
                continue

            if ctx.state == RunState.TEST:
                commands = ctx.execution_plan.tests_to_run if ctx.execution_plan else []
                for command in commands:
                    ctx.tool_results.append(self.tool_registry.run("run_test", command=command))
                ctx.state = next_state(ctx.state)
                continue

            if ctx.state == RunState.REVIEW:
                ctx.review_report = self.reviewer.run(ctx)
                self._log(ctx, "review_completed", asdict(ctx.review_report))
                ctx.state = RunState.DONE if ctx.review_report.decision == "pass" else RunState.RECOVER
                continue

            if ctx.state == RunState.RECOVER:
                ctx.recovery_action = self.recovery_manager.run(ctx)
                if ctx.recovery_action.rollback_files and ctx.edit_result:
                    for rel_path in ctx.recovery_action.rollback_files:
                        original = ctx.edit_result.original_contents.get(rel_path)
                        if original is None:
                            continue
                        restore_result = self.tool_registry.run(
                            "write_file",
                            path=str(Path(ctx.task_input.repo_root) / rel_path),
                            content=original,
                        )
                        ctx.tool_results.append(restore_result)
                self._log(ctx, "recovery_decided", asdict(ctx.recovery_action))
                ctx.failure_reason = ctx.recovery_action.reason
                ctx.recovery_attempts += 1
                ctx.state = RunState(ctx.recovery_action.next_state)
                continue

            ctx.failure_reason = f"Unhandled state: {ctx.state}"
            ctx.state = RunState.FAILED

        self._log(
            ctx,
            "run_finished",
            {
                "state": ctx.state,
                "failure_reason": ctx.failure_reason,
                "tool_calls": len(ctx.tool_results),
            },
        )
        return ctx

    def _analyze_task(self, ctx: RunContext) -> TaskSpec:
        text = ctx.task_input.raw_text.strip()
        lowered = text.lower()
        if "test" in lowered:
            task_type = "add_test"
        elif "bug" in lowered or "fix" in lowered:
            task_type = "bug_fix"
        elif "refactor" in lowered:
            task_type = "refactor"
        else:
            task_type = "add_feature"

        spec = TaskSpec(
            task_type=task_type,
            target=text[:120] or "unspecified target",
            intent=text,
            constraints=[
                "keep changes controlled",
                "respect safety guard",
            ],
        )
        self._log(ctx, "task_analyzed", asdict(spec))
        return spec

    def _build_plan(self, ctx: RunContext) -> list[str]:
        repo_root = Path(ctx.task_input.repo_root)
        plan = [
            f"Inspect repository at {repo_root}",
            "Use repo map to narrow candidate files",
            "Validate target contract before editing",
            "Check likely impact on callers and tests",
            "Create a safe checkpoint before any edits",
        ]
        if ctx.repo_map is not None:
            plan.append(ctx.repo_map.summary)
        if ctx.contract_report is not None:
            plan.append(ctx.contract_report.summary)
        if ctx.impact_report is not None:
            plan.append(ctx.impact_report.summary)
        if ctx.execution_plan and ctx.execution_plan.tests_to_run:
            for command in ctx.execution_plan.tests_to_run:
                plan.append(f"Run validation command: {command}")
        elif ctx.task_input.test_command:
            plan.append(f"Run validation command: {ctx.task_input.test_command}")
        else:
            plan.append("Skip test execution because no test command was provided")
        self._log(ctx, "plan_built", {"steps": plan})
        return plan

    def _log(self, ctx: RunContext, event_type: str, payload: dict) -> None:
        path = self.logger.write(ctx.run_id, event_type, payload)
        ctx.log_path = str(path)
