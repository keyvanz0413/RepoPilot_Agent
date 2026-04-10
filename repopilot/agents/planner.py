from __future__ import annotations

import importlib.util
from dataclasses import dataclass
from pathlib import Path

from repopilot.schemas.plan import ExecutionPlan, PlanStep
from repopilot.schemas.run_context import RunContext


@dataclass
class _FileCandidate:
    path: str
    score: int
    reason: str


class Planner:
    INSTRUCTION_FILES = {"CLAUDE.md", "AGENTS.md", ".repopilot/instructions.md", "README.md"}
    EDIT_TASK_TYPES = {"bug_fix", "refactor", "add_feature", "add_test"}
    ANALYSIS_TASK_TYPES = {"explain_repo", "explain_target"}

    def run(self, ctx: RunContext) -> ExecutionPlan:
        files_to_edit, edit_scope_reason = self._select_files_to_edit(ctx)
        plan_kind = self._plan_kind(ctx)
        requires_edit = plan_kind != "analyze"
        executor_choice = self._executor_choice(ctx, plan_kind)
        steps = self._build_steps(ctx, files_to_edit, plan_kind)
        tests_to_run: list[str] = self._select_tests(ctx)
        return ExecutionPlan(
            goal=ctx.task_input.raw_text,
            plan_kind=plan_kind,
            requires_edit=requires_edit,
            executor_choice=executor_choice,
            steps=steps,
            files_to_edit=files_to_edit if requires_edit else [],
            edit_scope_reason=edit_scope_reason,
            tests_to_run=tests_to_run if requires_edit else [],
            success_criteria=self._success_criteria(ctx, plan_kind, requires_edit),
            approval_required=self._approval_required(ctx, executor_choice),
            risk_level=ctx.impact_report.risk_level if ctx.impact_report else "medium",
            summary=self._summary_for_plan_kind(plan_kind),
        )

    def _build_steps(self, ctx: RunContext, files_to_edit: list[str], plan_kind: str) -> list[PlanStep]:
        if plan_kind == "analyze":
            inspect_files = list(ctx.contract_report.matched_files) if ctx.contract_report else []
            related_files = list(ctx.impact_report.affected_files) if ctx.impact_report else []
            return [
                PlanStep(
                    title="Inspect target",
                    description="Read the validated target files and summarize their role.",
                    files_involved=inspect_files,
                ),
                PlanStep(
                    title="Trace references",
                    description="Review related files and references to explain behavior.",
                    files_involved=related_files,
                ),
                PlanStep(
                    title="Report findings",
                    description="Produce an explanation without modifying repository files.",
                    files_involved=[],
                ),
            ]

        if plan_kind == "doc_update":
            return [
                PlanStep(
                    title="Inspect target",
                    description="Read the target documentation files and collect relevant repo context.",
                    files_involved=files_to_edit,
                ),
                PlanStep(
                    title="Apply doc update",
                    description="Update the documentation inside the approved file scope.",
                    files_involved=files_to_edit,
                ),
                PlanStep(
                    title="Review wording",
                    description="Check the updated documentation for consistency and clarity.",
                    files_involved=files_to_edit,
                ),
            ]

        if plan_kind == "test_update":
            return [
                PlanStep(
                    title="Inspect target",
                    description="Review the validated code target and infer the test surface.",
                    files_involved=files_to_edit,
                ),
                PlanStep(
                    title="Create or update tests",
                    description="Write tests inside the approved test file scope.",
                    files_involved=files_to_edit,
                ),
                PlanStep(
                    title="Verify test artifact",
                    description="Confirm the managed test file matches the requested target.",
                    files_involved=files_to_edit,
                ),
            ]

        return [
            PlanStep(
                title="Inspect target",
                description="Use repo map and contract matches to narrow edit scope.",
                files_involved=files_to_edit,
            ),
            PlanStep(
                title="Validate impact",
                description="Review references and test files before editing.",
                files_involved=ctx.impact_report.affected_files if ctx.impact_report else [],
            ),
            PlanStep(
                title="Apply minimal patch",
                description="Apply a controlled change inside the approved edit scope.",
                files_involved=files_to_edit,
            ),
        ]

    def _plan_kind(self, ctx: RunContext) -> str:
        task_type = ctx.task_spec.task_type if ctx.task_spec else ""
        if task_type in self.ANALYSIS_TASK_TYPES:
            return "analyze"
        if task_type == "doc_update":
            return "doc_update"
        if task_type == "add_test":
            return "test_update"
        return "code_edit"

    def _executor_choice(self, ctx: RunContext, plan_kind: str) -> str:
        if plan_kind == "analyze":
            return "analysis"
        if plan_kind == "doc_update":
            return "builtin_doc"
        if plan_kind == "test_update":
            return "builtin_test"
        if ctx.contract_report and ctx.contract_report.code_targets:
            return "codex"
        return "builtin_code"

    def _summary_for_plan_kind(self, plan_kind: str) -> str:
        if plan_kind == "analyze":
            return "Built an analysis plan from validated targets and impact context."
        if plan_kind == "doc_update":
            return "Built a documentation update plan from validated file targets."
        if plan_kind == "test_update":
            return "Built a test update plan from validated code targets and impact context."
        return "Built a conservative execution plan from repo context."

    def _success_criteria(
        self,
        ctx: RunContext,
        plan_kind: str,
        requires_edit: bool,
    ) -> list[str]:
        if plan_kind == "analyze":
            return [
                "Summarize the validated target and related references.",
                "Do not modify repository files.",
            ]
        if plan_kind == "doc_update":
            return [
                "Modify only the approved documentation files.",
                "Keep the documentation update inside the managed block.",
            ]
        if plan_kind == "test_update":
            return [
                "Create or update at least one approved test file.",
                "Keep the test change scoped to the validated target.",
            ]
        criteria = [
            "Modify only files inside the approved edit scope.",
            "Preserve behavior outside the intended change.",
        ]
        if requires_edit and ctx.contract_report and ctx.contract_report.function_contracts:
            criteria.append("Keep the function-level patch aligned with the validated contract.")
        if requires_edit and ctx.contract_report and ctx.contract_report.code_targets:
            criteria.append("Use the file-level code target set as the maximum edit boundary.")
        return criteria

    def _approval_required(self, ctx: RunContext, executor_choice: str) -> bool:
        risk_level = ctx.impact_report.risk_level if ctx.impact_report else "low"
        return executor_choice == "codex" and risk_level == "high"

    def _select_tests(self, ctx: RunContext) -> list[str]:
        if ctx.task_input.test_command:
            return [ctx.task_input.test_command]
        if (
            ctx.task_spec
            and ctx.task_spec.task_type == "add_test"
            and importlib.util.find_spec("pytest") is not None
        ):
            test_targets = self._infer_test_targets(ctx)
            if test_targets:
                joined = " ".join(test_targets[:5])
                return [f"python3 -m pytest {joined}"]
        if (
            ctx.impact_report
            and ctx.impact_report.related_tests
            and importlib.util.find_spec("pytest") is not None
        ):
            joined = " ".join(ctx.impact_report.related_tests[:5])
            return [f"python3 -m pytest {joined}"]
        return []

    def _select_files_to_edit(self, ctx: RunContext) -> tuple[list[str], str]:
        if ctx.task_spec and ctx.task_spec.task_type == "add_test":
            test_targets = self._infer_test_targets(ctx)
            if test_targets:
                return test_targets, "Use inferred test file targets for add_test tasks."

        explicit_targets = self._filter_editable_files(
            list(ctx.task_spec.target_files) if ctx.task_spec else []
        )
        if explicit_targets:
            if not self._should_expand_explicit_targets(ctx, explicit_targets):
                return explicit_targets[:4], "Use explicit target files as the edit scope."
            supplemental = self._select_supplemental_files(ctx, explicit_targets)
            files = explicit_targets + [path for path in supplemental if path not in explicit_targets]
            reason = "Use explicit target files as the primary edit scope."
            if supplemental:
                reason += " Add a minimal supplemental scope from validated or impacted implementation files."
            return files[:4], reason

        ranked = self._rank_file_candidates(ctx)
        if ranked:
            return (
                [item.path for item in ranked[:8]],
                "; ".join(f"{item.path}: {item.reason}" for item in ranked[:3]),
            )

        if ctx.contract_report and ctx.contract_report.matched_files:
            return (
                list(dict.fromkeys(ctx.contract_report.matched_files)),
                "Use validated contract matches as the edit scope.",
            )

        return [], "No safe edit scope could be inferred from current context."

    def _rank_file_candidates(self, ctx: RunContext) -> list[_FileCandidate]:
        scored: dict[str, _FileCandidate] = {}

        def add(path: str, score: int, reason: str) -> None:
            filtered = self._filter_editable_files([path])
            if not filtered:
                return
            candidate_path = filtered[0]
            if self._is_instruction_only_file(candidate_path) and candidate_path not in (ctx.task_spec.target_files if ctx.task_spec else []):
                return
            existing = scored.get(candidate_path)
            if existing is None or score > existing.score:
                scored[candidate_path] = _FileCandidate(candidate_path, score, reason)

        if ctx.task_spec:
            for path in ctx.task_spec.target_files:
                add(path, 120, "explicit target file from task analysis")

        if ctx.contract_report and ctx.contract_report.matched_files:
            for path in ctx.contract_report.matched_files:
                add(path, 100, "validated contract match")

        if ctx.local_retrieval_report:
            for path in ctx.local_retrieval_report.inspected_files:
                add(path, 80, "inspected during local retrieval")
            for path in ctx.local_retrieval_report.matched_files:
                add(path, 60, "matched during local retrieval")

        for path in self._find_files_mentioned_in_task(ctx):
            add(path, 70, "explicitly mentioned by task")

        if ctx.impact_report and ctx.impact_report.affected_files:
            for path in ctx.impact_report.affected_files:
                add(path, 50, "affected by impact analysis")

        return sorted(scored.values(), key=lambda item: (-item.score, item.path))

    def _filter_editable_files(self, files: list[str]) -> list[str]:
        allowed_suffixes = {".py", ".js", ".ts", ".tsx", ".md", ".json", ".toml", ".yaml", ".yml"}
        deduped: list[str] = []
        seen: set[str] = set()
        for path in files:
            if path in seen:
                continue
            seen.add(path)
            suffix = Path(path).suffix.lower()
            if suffix not in allowed_suffixes:
                continue
            deduped.append(path)
        return deduped[:8]

    def _is_instruction_only_file(self, path: str) -> bool:
        return path in self.INSTRUCTION_FILES

    def _select_supplemental_files(self, ctx: RunContext, primary_files: list[str]) -> list[str]:
        supplemental: list[str] = []
        seen = set(primary_files)

        for path in (ctx.contract_report.matched_files if ctx.contract_report else []):
            if path in seen:
                continue
            filtered = self._filter_editable_files([path])
            if not filtered:
                continue
            seen.add(filtered[0])
            supplemental.append(filtered[0])

        for path in (ctx.impact_report.affected_files if ctx.impact_report else []):
            if path in seen:
                continue
            filtered = self._filter_editable_files([path])
            if not filtered:
                continue
            candidate = filtered[0]
            if self._is_instruction_only_file(candidate):
                continue
            seen.add(candidate)
            supplemental.append(candidate)

        return supplemental[:2]

    def _should_expand_explicit_targets(self, ctx: RunContext, primary_files: list[str]) -> bool:
        task_type = ctx.task_spec.task_type if ctx.task_spec else ""
        if task_type not in self.EDIT_TASK_TYPES:
            return False

        if all(self._is_instruction_only_file(path) or Path(path).suffix.lower() == ".md" for path in primary_files):
            return False

        contract_matches = list(ctx.contract_report.matched_files) if ctx.contract_report else []
        impact_matches = list(ctx.impact_report.affected_files) if ctx.impact_report else []
        return bool(contract_matches or impact_matches)

    def _find_files_mentioned_in_task(self, ctx: RunContext) -> list[str]:
        task_text = ctx.task_input.raw_text.lower()
        candidates = ["README.md", "pyproject.toml"]
        if ctx.repo_map is not None:
            candidates.extend(node.path for node in ctx.repo_map.nodes)

        matched: list[str] = []
        seen: set[str] = set()
        for path in candidates:
            normalized = path.lower()
            basename = Path(path).name.lower()
            stem = Path(path).stem.lower()
            if normalized in task_text or basename in task_text or stem in task_text:
                if path not in seen:
                    seen.add(path)
                    matched.append(path)
        return self._filter_editable_files(matched)

    def _infer_test_targets(self, ctx: RunContext) -> list[str]:
        candidates: list[str] = []
        seen: set[str] = set()

        if ctx.impact_report and ctx.impact_report.related_tests:
            for path in ctx.impact_report.related_tests:
                filtered = self._filter_editable_files([path])
                if not filtered:
                    continue
                candidate = filtered[0]
                if candidate not in seen:
                    seen.add(candidate)
                    candidates.append(candidate)

        if ctx.task_spec:
            for path in ctx.task_spec.target_files:
                test_path = self._derived_test_path(path)
                if test_path and test_path not in seen:
                    seen.add(test_path)
                    candidates.append(test_path)

        return candidates[:4]

    def _derived_test_path(self, source_path: str) -> str | None:
        source = Path(source_path)
        if source.suffix != ".py":
            return None
        return str(Path("tests") / f"test_{source.stem}.py")
