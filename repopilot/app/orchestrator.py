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
from repopilot.core.local_retriever import LocalRetriever
from repopilot.core.recovery_manager import RecoveryManager
from repopilot.core.repo_mapper import RepoMapper
from repopilot.core.retrieval_decider import RetrievalDecider
from repopilot.schemas.edit import EditResult
from repopilot.schemas.enums import RunState
from repopilot.schemas.retrieval import RetrievalLevel
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
        self.local_retriever = LocalRetriever(tool_registry, ".")
        self.retrieval_decider = RetrievalDecider()
        self.planner = Planner()
        self.reviewer = Reviewer()
        self.recovery_manager = RecoveryManager()
        self.coder = Coder(tool_registry, ".")

    def run(self, ctx: RunContext) -> RunContext:
        coder_executor = self.coder.executor
        self.repo_mapper = RepoMapper(ctx.task_input.repo_root)
        self.contract_validator = ContractValidator(ctx.task_input.repo_root)
        self.impact_analyzer = ImpactAnalyzer(ctx.task_input.repo_root)
        self.local_retriever = LocalRetriever(self.tool_registry, ctx.task_input.repo_root)
        self.coder = Coder(self.tool_registry, ctx.task_input.repo_root, executor=coder_executor)
        ctx.available_executors = ["builtin"]
        if coder_executor is not None:
            ctx.available_executors.append("codex")
        self._log(ctx, "run_started", {"repo_root": ctx.task_input.repo_root})

        while ctx.state not in TERMINAL_STATES:
            self._log(ctx, "state_enter", {"state": ctx.state})

            if ctx.state == RunState.INIT:
                ctx.state = next_state(ctx.state)
                continue

            if ctx.state == RunState.TASK_INTAKE:
                ctx.task_spec = self._analyze_task(ctx)
                ctx.state = next_state(ctx.state)
                continue

            if ctx.state == RunState.RETRIEVE:
                if ctx.task_spec is None:
                    ctx.failure_reason = "Task spec missing before retrieval stage"
                    ctx.state = RunState.FAILED
                    continue
                self._run_retrieval_stage(ctx)
                if ctx.failure_reason:
                    ctx.state = RunState.FAILED
                    continue
                ctx.state = next_state(ctx.state)
                continue

            if ctx.state == RunState.PLAN:
                ctx.execution_plan = self.planner.run(ctx)
                self._log(ctx, "execution_plan_built", asdict(ctx.execution_plan))
                ctx.plan_steps = self._build_plan(ctx)
                ctx.state = next_state(ctx.state)
                continue

            if ctx.state == RunState.ACT:
                if ctx.execution_plan and ctx.execution_plan.requires_edit:
                    checkpoint_result = self.tool_registry.run("create_checkpoint")
                    ctx.tool_results.append(checkpoint_result)
                    ctx.checkpoint_ref = checkpoint_result.data.get("checkpoint_ref")
                    ctx.edit_result = self.coder.run(ctx)
                else:
                    ctx.edit_result = EditResult(
                        applied=True,
                        changed_files=[],
                        summary="No repository edits were required for this plan.",
                    )
                self._log(ctx, "edit_attempted", asdict(ctx.edit_result))
                ctx.state = next_state(ctx.state)
                continue

            if ctx.state == RunState.VERIFY:
                commands = ctx.execution_plan.tests_to_run if ctx.execution_plan else []
                for command in commands:
                    ctx.tool_results.append(self.tool_registry.run("run_test", command=command))
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
                recovery_next_state = RunState(ctx.recovery_action.next_state)
                if ctx.recovery_action.next_executor and ctx.execution_plan is not None:
                    ctx.execution_plan.executor_choice = ctx.recovery_action.next_executor
                if recovery_next_state in {RunState.ACT, RunState.PLAN, RunState.RETRIEVE}:
                    ctx.failure_reason = None
                    ctx.review_report = None
                    ctx.edit_result = None
                    if recovery_next_state == RunState.PLAN:
                        ctx.execution_plan = None
                    if ctx.recovery_action.rollback_files:
                        ctx.checkpoint_ref = None
                self._log(ctx, "recovery_decided", asdict(ctx.recovery_action))
                ctx.recovery_attempts += 1
                if recovery_next_state == RunState.FAILED:
                    ctx.failure_reason = ctx.recovery_action.reason
                ctx.state = recovery_next_state
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

    def _run_retrieval_stage(self, ctx: RunContext) -> None:
        if ctx.task_spec is None:
            ctx.failure_reason = "Task spec missing before retrieval stage"
            return

        ctx.retrieval_trace.clear()
        ctx.retrieval_decision = self.retrieval_decider.run(ctx.task_spec)
        self._log(ctx, "retrieval_decided", asdict(ctx.retrieval_decision))

        for _ in range(3):
            if ctx.retrieval_decision is None:
                ctx.failure_reason = "Retrieval decision missing during retrieval stage"
                return

            ctx.retrieval_trace.append(f"level:{ctx.retrieval_decision.retrieval_level.value}")

            if ctx.retrieval_decision.retrieval_level == RetrievalLevel.LOCAL:
                ctx.local_retrieval_report = self.local_retriever.run(ctx.retrieval_decision)
                self._log(ctx, "local_retrieval_completed", asdict(ctx.local_retrieval_report))
            elif ctx.retrieval_decision.retrieval_level == RetrievalLevel.GLOBAL:
                ctx.repo_map = self.repo_mapper.run()
                self._log(ctx, "repo_mapped", asdict(ctx.repo_map))

            if ctx.task_spec.task_type == "explain_repo" and ctx.repo_map is not None:
                ctx.retrieval_trace.append("stop:repo_map_ready")
                return

            ctx.contract_report = self.contract_validator.run(
                ctx.task_spec,
                candidate_files=self._candidate_files_for_contract(ctx),
            )
            self._log(ctx, "contract_validated", asdict(ctx.contract_report))
            ctx.impact_report = self.impact_analyzer.run(
                ctx.contract_report,
                candidate_files=self._candidate_files_for_impact(ctx),
                task_spec=ctx.task_spec,
            )
            self._log(ctx, "impact_analyzed", asdict(ctx.impact_report))

            if self._retrieval_complete(ctx):
                ctx.retrieval_trace.append("stop:context_sufficient")
                return
            if self._can_escalate_retrieval(ctx):
                self._escalate_retrieval(ctx)
                continue

            ctx.retrieval_trace.append("stop:no_additional_retrieval_action")
            return

        ctx.retrieval_trace.append("stop:retrieval_budget_exhausted")

    def _retrieval_complete(self, ctx: RunContext) -> bool:
        if ctx.task_spec is None:
            return False
        if ctx.task_spec.task_type == "explain_repo":
            return ctx.repo_map is not None
        if ctx.task_spec.task_type in {"doc_update", "explain_target"}:
            return bool(ctx.contract_report and ctx.contract_report.matched_files and ctx.impact_report)
        if ctx.task_spec.task_type in {"bug_fix", "add_feature", "refactor", "add_test"}:
            return bool(
                ctx.contract_report
                and (ctx.contract_report.function_contracts or ctx.contract_report.code_targets)
                and ctx.impact_report is not None
            )
        return bool(ctx.contract_report and ctx.impact_report)

    def _can_escalate_retrieval(self, ctx: RunContext) -> bool:
        if ctx.retrieval_decision is None:
            return False
        if ctx.retrieval_decision.retrieval_level != RetrievalLevel.LOCAL:
            return False
        if ctx.retrieval_escalations > 0:
            return False
        return self._should_escalate_after_contract(ctx) or self._should_escalate_after_impact(ctx)

    def _escalate_retrieval(self, ctx: RunContext) -> None:
        if ctx.retrieval_decision is None:
            return
        ctx.retrieval_escalations += 1
        ctx.retrieval_decision.retrieval_level = RetrievalLevel.GLOBAL
        ctx.retrieval_decision.fallback_used = True
        ctx.retrieval_decision.reason = (
            "Retrieval stage escalated to GLOBAL after local context was not sufficient."
        )
        ctx.retrieval_decision.summary = (
            f"Retrieval decision: {ctx.retrieval_decision.retrieval_level.value}"
            f" for {ctx.task_spec.task_type if ctx.task_spec else 'task'} after escalation."
        )
        ctx.retrieval_trace.append("action:escalate_to_global")
        self._log(
            ctx,
            "retrieval_escalated",
            {
                "retrieval_level": ctx.retrieval_decision.retrieval_level,
                "retrieval_escalations": ctx.retrieval_escalations,
            },
        )

    def _analyze_task(self, ctx: RunContext) -> TaskSpec:
        text = ctx.task_input.raw_text.strip()
        lowered = text.lower()
        target_files = self._extract_target_files(text)
        target_symbols = self._extract_target_symbols(text)
        scope_hint = self._infer_scope_hint(text, target_files, target_symbols)
        task_type = self._infer_task_type(text, lowered, target_files, scope_hint)

        spec = TaskSpec(
            task_type=task_type,
            target=text[:120] or "unspecified target",
            intent=text,
            target_symbols=target_symbols,
            target_files=target_files,
            scope_hint=scope_hint,
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
            "Run retrieval as a dynamic stage before planning",
            "Build a plan contract with executor choice and success criteria",
        ]
        if ctx.execution_plan and ctx.execution_plan.requires_edit:
            plan.append("Create a safe checkpoint before any edits")
        else:
            plan.append("Skip checkpoint because this plan does not edit repository files")
        if ctx.retrieval_trace:
            plan.extend(f"Retrieval trace: {item}" for item in ctx.retrieval_trace)
        if ctx.repo_map is not None:
            plan.append(ctx.repo_map.summary)
        if ctx.local_retrieval_report is not None:
            plan.append(ctx.local_retrieval_report.summary)
        if ctx.retrieval_decision is not None:
            plan.append(ctx.retrieval_decision.summary)
        if ctx.contract_report is not None:
            plan.append(ctx.contract_report.summary)
        if ctx.impact_report is not None:
            plan.append(ctx.impact_report.summary)
        if ctx.execution_plan and ctx.execution_plan.tests_to_run:
            for command in ctx.execution_plan.tests_to_run:
                plan.append(f"Run validation command: {command}")
        elif ctx.task_input.test_command:
            plan.append(f"Run validation command: {ctx.task_input.test_command}")
        elif ctx.execution_plan and not ctx.execution_plan.requires_edit:
            plan.append("No test execution is required for this plan")
        else:
            plan.append("Skip test execution because no test command was provided")
        self._log(ctx, "plan_built", {"steps": plan})
        return plan

    def _log(self, ctx: RunContext, event_type: str, payload: dict) -> None:
        path = self.logger.write(ctx.run_id, event_type, payload)
        ctx.log_path = str(path)

    def _candidate_files_for_contract(self, ctx: RunContext) -> list[str] | None:
        if ctx.task_spec and ctx.task_spec.target_files:
            return list(ctx.task_spec.target_files)
        if ctx.local_retrieval_report and ctx.local_retrieval_report.matched_files:
            return list(ctx.local_retrieval_report.matched_files)
        if ctx.repo_map is not None:
            preferred = [
                node.path
                for node in ctx.repo_map.nodes
                if node.node_type in {"module", "service", "schema"} and node.path.endswith(".py")
            ]
            return preferred[:20] or None
        return None

    def _candidate_files_for_impact(self, ctx: RunContext) -> list[str] | None:
        candidates: list[str] = []
        seen: set[str] = set()
        if ctx.task_spec and ctx.task_spec.target_files:
            for path in ctx.task_spec.target_files:
                if path not in seen:
                    seen.add(path)
                    candidates.append(path)
        for path in (ctx.contract_report.matched_files if ctx.contract_report else []):
            if path not in seen:
                seen.add(path)
                candidates.append(path)
        if ctx.local_retrieval_report:
            for path in ctx.local_retrieval_report.matched_files:
                if path not in seen:
                    seen.add(path)
                    candidates.append(path)
        return candidates or None

    def _should_escalate_after_contract(self, ctx: RunContext) -> bool:
        if ctx.retrieval_decision is None or ctx.contract_report is None:
            return False
        if ctx.task_spec and ctx.task_spec.task_type in {"doc_update", "explain_target"}:
            return False
        if (
            ctx.contract_report.function_contracts
            or ctx.contract_report.code_targets
            or ctx.contract_report.matched_files
        ):
            return False
        return True

    def _should_escalate_after_impact(self, ctx: RunContext) -> bool:
        if ctx.retrieval_decision is None or ctx.impact_report is None:
            return False
        if ctx.task_spec and ctx.task_spec.task_type in {"doc_update", "explain_target"}:
            return False
        return not ctx.impact_report.affected_files

    def _extract_target_files(self, text: str) -> list[str]:
        candidates = [
            "README.md",
            "pyproject.toml",
            "repopilot/app/state_machine.py",
            "repopilot/app/orchestrator.py",
            "repopilot/agents/planner.py",
            "repopilot/agents/coder.py",
        ]
        lowered = text.lower()
        matched: list[str] = []
        seen: set[str] = set()
        for path in candidates:
            path_lower = path.lower()
            stem = Path(path).stem.lower()
            if path_lower in lowered or stem in lowered:
                if path not in seen:
                    seen.add(path)
                    matched.append(path)
        return matched[:8]

    def _extract_target_symbols(self, text: str) -> list[str]:
        symbols: list[str] = []
        seen: set[str] = set()
        for token in text.replace("`", " ").split():
            normalized = token.strip(".,:;()[]{}")
            if "_" not in normalized and not normalized[:1].isalpha():
                continue
            if len(normalized) < 3:
                continue
            if normalized not in seen and any(ch == "_" for ch in normalized):
                seen.add(normalized)
                symbols.append(normalized)
        return symbols[:8]

    def _infer_scope_hint(
        self,
        text: str,
        target_files: list[str],
        target_symbols: list[str],
    ) -> str:
        lowered = text.lower()
        if any(term in lowered for term in ("repo", "architecture", "workflow", "system")) or any(
            term in text for term in ("仓库", "架构", "整体", "项目")
        ):
            return "repo"
        if target_files:
            return "file"
        if target_symbols:
            return "symbol"
        return "unknown"

    def _infer_task_type(
        self,
        text: str,
        lowered: str,
        target_files: list[str],
        scope_hint: str,
    ) -> str:
        if "explain" in lowered or "analyze" in lowered or "解释" in text or "分析" in text:
            return "explain_repo" if scope_hint == "repo" else "explain_target"
        if target_files and all(Path(path).suffix.lower() == ".md" for path in target_files):
            return "doc_update"
        if "readme" in lowered and any(term in lowered for term in ("update", "edit", "修改", "更新")):
            return "doc_update"
        if "test" in lowered:
            return "add_test"
        if "bug" in lowered or "fix" in lowered:
            return "bug_fix"
        if "refactor" in lowered:
            return "refactor"
        return "add_feature"
