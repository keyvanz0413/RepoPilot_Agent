from __future__ import annotations

import re
from pathlib import Path

from repopilot.models.codex import CodexExecutor
from repopilot.core.repo_instructions import RepoInstructionLoader
from repopilot.schemas.edit import CodexEditRequest, CodexReferenceSnippet, EditResult
from repopilot.schemas.run_context import RunContext
from repopilot.tools.tool_registry import ToolRegistry


class Coder:
    PARAMETER_NAME = "repopilot_flag: bool = False"
    DOC_UPDATE_BEGIN = "<!-- repopilot-doc-update:begin -->"
    DOC_UPDATE_END = "<!-- repopilot-doc-update:end -->"
    CODE_TASK_TYPES = {"bug_fix", "add_feature", "refactor"}
    TEST_TASK_TYPES = {"add_test"}

    def __init__(
        self,
        tool_registry: ToolRegistry,
        repo_root: str,
        executor: CodexExecutor | None = None,
    ) -> None:
        self.tool_registry = tool_registry
        self.repo_root = Path(repo_root).resolve()
        self.executor = executor
        self.instruction_loader = RepoInstructionLoader(str(self.repo_root))

    def run(self, ctx: RunContext) -> EditResult:
        if ctx.execution_plan is None or ctx.contract_report is None:
            return EditResult(applied=False, summary="Execution plan or contract report is missing.")

        task_type = ctx.task_spec.task_type if ctx.task_spec else ""
        executor_choice = ctx.execution_plan.executor_choice if ctx.execution_plan else "builtin_code"

        if executor_choice == "analysis":
            return EditResult(applied=True, changed_files=[], summary="Analysis plan does not execute edits.")

        if executor_choice == "codex":
            if self.executor is None:
                return EditResult(
                    applied=False,
                    summary="Plan selected the Codex executor, but no Codex executor is configured.",
                )
            return self._run_codex_executor(ctx)

        if executor_choice == "builtin_doc" or task_type == "doc_update":
            return self._run_doc_update(ctx)
        if executor_choice == "builtin_test" or task_type in self.TEST_TASK_TYPES:
            return self._run_builtin_test_update(ctx)
        if executor_choice == "builtin_code" and task_type == "bug_fix":
            return self._run_builtin_bug_fix(ctx)
        if executor_choice == "builtin_code" and task_type == "add_feature":
            return self._run_builtin_feature_edit(ctx)
        if executor_choice == "builtin_code" and task_type == "refactor":
            return self._run_builtin_refactor_edit(ctx)

        return EditResult(
            applied=False,
            summary=f"Builtin coder does not support task type '{task_type or 'unknown'}'.",
        )

    def _run_builtin_bug_fix(self, ctx: RunContext) -> EditResult:
        if self._supports_optional_parameter_task(ctx.task_input.raw_text):
            return self._run_optional_parameter_edit(ctx)
        return EditResult(
            applied=False,
            summary=(
                "Builtin bug-fix editor currently supports only optional-parameter style fixes. "
                "Use the Codex executor for broader bug-fix tasks."
            ),
        )

    def _run_builtin_feature_edit(self, ctx: RunContext) -> EditResult:
        if self._supports_optional_parameter_task(ctx.task_input.raw_text):
            return self._run_optional_parameter_edit(ctx)
        return EditResult(
            applied=False,
            summary=(
                "Builtin feature editor only supports optional-parameter style feature changes. "
                "Use the Codex executor for broader feature work."
            ),
        )

    def _run_builtin_refactor_edit(self, ctx: RunContext) -> EditResult:
        if not self._supports_optional_parameter_task(ctx.task_input.raw_text):
            return EditResult(
                applied=False,
                summary=(
                    "Builtin refactor editor does not implement general structural refactors yet. "
                    "Use the Codex executor for refactor tasks."
                ),
            )

        return self._run_optional_parameter_edit(ctx)

    def _run_optional_parameter_edit(self, ctx: RunContext) -> EditResult:
        contract = ctx.contract_report.function_contracts[0] if ctx.contract_report.function_contracts else None
        if contract is None:
            if ctx.contract_report.code_targets:
                target_paths = ", ".join(target.path for target in ctx.contract_report.code_targets[:3])
                return EditResult(
                    applied=False,
                    summary=(
                        "Validated file-level code targets are available, but builtin code editing still "
                        "requires a concrete function contract. Use the Codex executor for file-level code tasks."
                    ),
                    errors=[f"File-level targets: {target_paths}"],
                )
            return EditResult(applied=False, summary="No function contract available for editing.")

        target_path = self.repo_root / contract.path
        original = target_path.read_text(encoding="utf-8")
        updated = self._patch_signature(original, contract.symbol)
        if updated is None:
            return EditResult(
                applied=False,
                summary="Could not patch the target function signature safely.",
                errors=[f"Unsupported signature format for {contract.symbol}"],
            )
        if updated == original:
            return EditResult(
                applied=True,
                changed_files=[],
                summary="Target signature already contains the managed parameter.",
            )

        tool_result = self.tool_registry.run("write_file", path=str(target_path), content=updated)
        if not tool_result.ok:
            return EditResult(applied=False, summary="write_file failed", errors=[tool_result.summary])

        return EditResult(
            applied=True,
            changed_files=[contract.path],
            summary=f"Added optional parameter to {contract.symbol} in {contract.path}.",
            original_contents={contract.path: original},
        )

    def _run_builtin_test_update(self, ctx: RunContext) -> EditResult:
        target_files = list(ctx.execution_plan.files_to_edit) if ctx.execution_plan else []
        if not target_files:
            return EditResult(applied=False, summary="No test file target was approved for editing.")

        rel_path = target_files[0]
        target_path = self.repo_root / rel_path
        try:
            original = target_path.read_text(encoding="utf-8")
        except OSError:
            original = ""

        updated = self._upsert_test_stub(original, ctx)
        if updated == original:
            return EditResult(
                applied=True,
                changed_files=[],
                summary="Test target already contains the managed test stub.",
            )

        tool_result = self.tool_registry.run("write_file", path=str(target_path), content=updated)
        if not tool_result.ok:
            return EditResult(applied=False, summary="write_file failed", errors=[tool_result.summary])

        return EditResult(
            applied=True,
            changed_files=[rel_path],
            summary=f"Updated the managed test stub in {rel_path}.",
            original_contents={rel_path: original},
        )

    def _run_doc_update(self, ctx: RunContext) -> EditResult:
        target_files = list(ctx.execution_plan.files_to_edit) if ctx.execution_plan else []
        if not target_files:
            return EditResult(applied=False, summary="No documentation file was approved for editing.")

        rel_path = target_files[0]
        target_path = self.repo_root / rel_path
        try:
            original = target_path.read_text(encoding="utf-8")
        except OSError as exc:
            return EditResult(
                applied=False,
                summary="Failed to read the documentation target.",
                errors=[str(exc)],
            )

        update_note = self._build_doc_update_note(ctx)
        updated = self._upsert_doc_update_block(original, update_note)
        if updated == original:
            return EditResult(
                applied=True,
                changed_files=[],
                summary="Documentation target already contains the managed update block.",
            )
        tool_result = self.tool_registry.run("write_file", path=str(target_path), content=updated)
        if not tool_result.ok:
            return EditResult(applied=False, summary="write_file failed", errors=[tool_result.summary])

        return EditResult(
            applied=True,
            changed_files=[rel_path],
            summary=f"Updated the managed documentation block in {rel_path}.",
            original_contents={rel_path: original},
        )

    def _run_codex_executor(self, ctx: RunContext) -> EditResult:
        request = self._build_codex_request(ctx)
        if not request.allowed_files:
            return EditResult(
                applied=False,
                summary="Execution plan did not define any allowed files for Codex editing.",
                errors=[ctx.execution_plan.edit_scope_reason if ctx.execution_plan else "Missing execution plan"],
                executor="codex",
            )
        try:
            proposed_edits, summary = self.executor.edit(request)
        except RuntimeError as exc:
            return EditResult(
                applied=False,
                summary="Codex executor failed before applying edits.",
                errors=[str(exc)],
                executor="codex",
            )
        if not proposed_edits:
            return EditResult(
                applied=False,
                summary="Codex executor returned no file edits.",
                executor="codex",
            )

        original_contents: dict[str, str] = {}
        changed_files: list[str] = []
        errors: list[str] = []

        for edit in proposed_edits:
            rel_path = edit.path
            if request.allowed_files and rel_path not in request.allowed_files:
                errors.append(f"Edit outside allowed files: {rel_path}")
                continue
            target_path = (self.repo_root / rel_path).resolve()
            try:
                original_contents[rel_path] = target_path.read_text(encoding="utf-8")
            except OSError as exc:
                errors.append(f"Failed to read {rel_path}: {exc}")
                continue
            tool_result = self.tool_registry.run(
                "write_file",
                path=str(target_path),
                content=edit.content,
            )
            if not tool_result.ok:
                errors.append(f"write_file failed for {rel_path}: {tool_result.summary}")
                continue
            changed_files.append(rel_path)

        if errors and not changed_files:
            return EditResult(
                applied=False,
                changed_files=[],
                summary="Codex executor could not apply any proposed edits.",
                errors=errors,
                original_contents=original_contents,
                executor="codex",
            )

        return EditResult(
            applied=True,
            changed_files=changed_files,
            summary=summary,
            errors=errors,
            original_contents=original_contents,
            executor="codex",
        )

    def _build_codex_request(self, ctx: RunContext) -> CodexEditRequest:
        allowed_files = list(ctx.execution_plan.files_to_edit) if ctx.execution_plan else []
        reference_snippets: list[CodexReferenceSnippet] = []
        if ctx.local_retrieval_report is not None:
            for snippet in ctx.local_retrieval_report.snippets[:5]:
                reference_snippets.append(
                    CodexReferenceSnippet(path=snippet.path, line=snippet.line, text=snippet.text)
                )
        if ctx.impact_report is not None:
            for ref in ctx.impact_report.references[:5]:
                reference_snippets.append(
                    CodexReferenceSnippet(path=ref.path, line=ref.line, text=ref.text)
                )

        return CodexEditRequest(
            request_version="v1",
            repo_root=str(self.repo_root),
            goal=ctx.task_input.raw_text,
            task_type=ctx.task_spec.task_type if ctx.task_spec else "",
            allowed_files=allowed_files,
            required_tests=list(ctx.execution_plan.tests_to_run) if ctx.execution_plan else [],
            constraints=list(ctx.task_spec.constraints) if ctx.task_spec else [],
            repo_instructions=self.instruction_loader.load(),
            editing_rules=self._editing_rules_for_task(ctx),
            testing_rules=self._testing_rules_for_task(ctx),
            plan_steps=[step.description for step in ctx.execution_plan.steps] if ctx.execution_plan else [],
            retrieval_summary=ctx.retrieval_decision.summary if ctx.retrieval_decision else "",
            contract_summary=ctx.contract_report.summary if ctx.contract_report else "",
            impact_summary=ctx.impact_report.summary if ctx.impact_report else "",
            plan_summary=ctx.execution_plan.summary if ctx.execution_plan else "",
            target_symbol=ctx.contract_report.matched_symbol if ctx.contract_report else None,
            contract_files=list(ctx.contract_report.matched_files) if ctx.contract_report else [],
            impact_files=list(ctx.impact_report.affected_files) if ctx.impact_report else [],
            reference_snippets=reference_snippets[:10],
        )

    def _supports_optional_parameter_task(self, task_text: str) -> bool:
        lowered = task_text.lower()
        return (
            "optional" in lowered
            or "可选参数" in task_text
            or ("参数" in task_text and "可选" in task_text)
        )

    def _editing_rules_for_task(self, ctx: RunContext) -> list[str]:
        task_type = ctx.task_spec.task_type if ctx.task_spec else ""
        base_rules = [
            "Only modify files listed in allowed_files.",
            "Preserve unrelated behavior and keep edits minimal.",
        ]
        if task_type == "doc_update":
            return base_rules + [
                "Keep documentation changes scoped to the approved markdown or text files.",
                "Do not change code files for documentation-only tasks.",
            ]
        if task_type == "add_test":
            return base_rules + [
                "Prefer adding or updating tests instead of changing production behavior.",
                "Keep new tests aligned with the validated target and impact scope.",
            ]
        return base_rules + [
            "Preserve public interfaces unless the task explicitly requires an interface change.",
            "Use the contract and impact summaries to avoid broad refactors.",
        ]

    def _testing_rules_for_task(self, ctx: RunContext) -> list[str]:
        task_type = ctx.task_spec.task_type if ctx.task_spec else ""
        rules = [
            "Prefer the required_tests list when validating changes.",
            "Do not invent new test commands outside the provided scope.",
        ]
        if task_type == "doc_update":
            return rules + ["Documentation-only updates do not require unrelated code tests by default."]
        if task_type == "add_test":
            return rules + ["Ensure the resulting changes leave a concrete test artifact in scope."]
        return rules

    def _build_doc_update_note(self, ctx: RunContext) -> str:
        return (
            f"{self.DOC_UPDATE_BEGIN}\n"
            "## RepoPilot Managed Update\n"
            f"- Request: {ctx.task_input.raw_text}\n"
            f"- Scope: {ctx.execution_plan.edit_scope_reason if ctx.execution_plan else 'n/a'}\n"
            f"- Plan: {ctx.execution_plan.summary if ctx.execution_plan else 'n/a'}\n"
            f"{self.DOC_UPDATE_END}"
        )

    def _upsert_doc_update_block(self, content: str, block: str) -> str:
        legacy_marker = "<!-- repopilot-doc-update -->"
        if self.DOC_UPDATE_BEGIN in content and self.DOC_UPDATE_END in content:
            start = content.index(self.DOC_UPDATE_BEGIN)
            end = content.index(self.DOC_UPDATE_END) + len(self.DOC_UPDATE_END)
            return content[:start].rstrip() + "\n\n" + block + "\n"

        if legacy_marker in content:
            start = content.index(legacy_marker)
            return content[:start].rstrip() + "\n\n" + block + "\n"

        return content.rstrip() + "\n\n" + block + "\n"

    def _upsert_test_stub(self, content: str, ctx: RunContext) -> str:
        begin = "# repopilot-test-stub:begin"
        end = "# repopilot-test-stub:end"
        target_symbol = ctx.contract_report.matched_symbol or (
            ctx.task_spec.target_symbols[0] if ctx.task_spec and ctx.task_spec.target_symbols else "target"
        )
        stub = (
            f"{begin}\n"
            "def test_repopilot_managed_stub():\n"
            f"    \"\"\"Managed placeholder test for {target_symbol}.\"\"\"\n"
            "    assert True\n"
            f"{end}"
        )

        if begin in content and end in content:
            start = content.index(begin)
            finish = content.index(end) + len(end)
            return content[:start].rstrip() + "\n\n" + stub + "\n"

        if not content.strip():
            return stub + "\n"

        return content.rstrip() + "\n\n" + stub + "\n"

    def _patch_signature(self, content: str, symbol: str) -> str | None:
        pattern = re.compile(
            rf"^(?P<indent>\s*)def {re.escape(symbol)}\((?P<params>[^)]*)\)(?P<tail>\s*->\s*[^:]+)?:",
            re.MULTILINE,
        )
        match = pattern.search(content)
        if match is None:
            return None

        params = match.group("params").strip()
        if self.PARAMETER_NAME in params:
            return content

        new_params = self.PARAMETER_NAME if not params else f"{params}, {self.PARAMETER_NAME}"
        replacement = f"{match.group('indent')}def {symbol}({new_params})"
        if match.group("tail"):
            replacement += match.group("tail")
        replacement += ":"
        start, end = match.span()
        return content[:start] + replacement + content[end:]
