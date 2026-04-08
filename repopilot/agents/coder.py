from __future__ import annotations

import re
from pathlib import Path

from repopilot.models.codex import CodexExecutor
from repopilot.schemas.edit import CodexEditRequest, EditResult, ProposedFileEdit
from repopilot.schemas.run_context import RunContext
from repopilot.tools.tool_registry import ToolRegistry


class Coder:
    PARAMETER_NAME = "repopilot_flag: bool = False"

    def __init__(
        self,
        tool_registry: ToolRegistry,
        repo_root: str,
        executor: CodexExecutor | None = None,
    ) -> None:
        self.tool_registry = tool_registry
        self.repo_root = Path(repo_root).resolve()
        self.executor = executor

    def run(self, ctx: RunContext) -> EditResult:
        if ctx.execution_plan is None or ctx.contract_report is None:
            return EditResult(applied=False, summary="Execution plan or contract report is missing.")

        if self.executor is not None:
            return self._run_codex_executor(ctx)

        if not self._supports_task(ctx.task_input.raw_text):
            return EditResult(applied=False, summary="Coder only supports optional-parameter tasks in this phase.")

        contract = ctx.contract_report.function_contracts[0] if ctx.contract_report.function_contracts else None
        if contract is None:
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

    def _run_codex_executor(self, ctx: RunContext) -> EditResult:
        request = self._build_codex_request(ctx)
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
        supporting_context: list[str] = []
        if ctx.local_retrieval_report is not None:
            for snippet in ctx.local_retrieval_report.snippets[:5]:
                supporting_context.append(f"{snippet.path}:{snippet.line}: {snippet.text}")
        if ctx.impact_report is not None:
            for ref in ctx.impact_report.references[:5]:
                supporting_context.append(f"{ref.path}:{ref.line}: {ref.text}")

        return CodexEditRequest(
            goal=ctx.task_input.raw_text,
            allowed_files=allowed_files,
            task_type=ctx.task_spec.task_type if ctx.task_spec else "",
            constraints=list(ctx.task_spec.constraints) if ctx.task_spec else [],
            retrieval_summary=ctx.retrieval_decision.summary if ctx.retrieval_decision else "",
            contract_summary=ctx.contract_report.summary if ctx.contract_report else "",
            impact_summary=ctx.impact_report.summary if ctx.impact_report else "",
            plan_summary=ctx.execution_plan.summary if ctx.execution_plan else "",
            supporting_context=supporting_context,
        )

    def _supports_task(self, task_text: str) -> bool:
        lowered = task_text.lower()
        return (
            "optional" in lowered
            or "可选参数" in task_text
            or ("参数" in task_text and "可选" in task_text)
        )

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
