from __future__ import annotations

import re
from pathlib import Path

from repopilot.schemas.edit import EditResult
from repopilot.schemas.run_context import RunContext
from repopilot.tools.tool_registry import ToolRegistry


class Coder:
    PARAMETER_NAME = "repopilot_flag: bool = False"

    def __init__(self, tool_registry: ToolRegistry, repo_root: str) -> None:
        self.tool_registry = tool_registry
        self.repo_root = Path(repo_root).resolve()

    def run(self, ctx: RunContext) -> EditResult:
        if ctx.execution_plan is None or ctx.contract_report is None:
            return EditResult(applied=False, summary="Execution plan or contract report is missing.")

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
