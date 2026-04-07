from __future__ import annotations

import ast
import re
from pathlib import Path

from repopilot.schemas.contract import ContractReport, FunctionContract
from repopilot.schemas.task import TaskSpec


class ContractValidator:
    SYMBOL_PATTERN = re.compile(r"`([^`]+)`|([A-Za-z_][A-Za-z0-9_]*)")
    STOP_WORDS = {
        "fix",
        "add",
        "update",
        "repo",
        "this",
        "file",
        "bug",
        "function",
        "issue",
        "login",
    }

    def __init__(self, repo_root: str) -> None:
        self.repo_root = Path(repo_root).resolve()

    def run(self, task_spec: TaskSpec) -> ContractReport:
        symbol = self._guess_symbol(task_spec)
        report = ContractReport(target=task_spec.target, matched_symbol=symbol)
        if not symbol:
            report.uncertainties.append("Could not infer target symbol from task text")
            report.summary = "No concrete symbol inferred for contract validation."
            return report

        for path in sorted(self.repo_root.rglob("*.py")):
            if ".git" in path.parts or "logs" in path.parts:
                continue
            contract = self._find_contract(path, symbol)
            if contract:
                rel = str(path.relative_to(self.repo_root))
                report.matched_files.append(rel)
                report.function_contracts.append(contract)

        if not report.function_contracts:
            report.uncertainties.append(f"Symbol '{symbol}' not found in Python source")
            report.summary = f"No Python function contract found for symbol '{symbol}'."
            return report

        report.summary = (
            f"Found {len(report.function_contracts)} contract match(es) for symbol '{symbol}'."
        )
        return report

    def _guess_symbol(self, task_spec: TaskSpec) -> str | None:
        repo_symbols = self._collect_repo_symbols()
        candidates: list[str] = []
        for source in (task_spec.target, task_spec.intent):
            for match in self.SYMBOL_PATTERN.finditer(source):
                token = match.group(1) or match.group(2)
                if not token:
                    continue
                if token.lower() in self.STOP_WORDS:
                    continue
                if token in repo_symbols:
                    return token
                if "_" in token:
                    candidates.append(token)
        return candidates[0] if candidates else None

    def _collect_repo_symbols(self) -> set[str]:
        symbols: set[str] = set()
        for path in self.repo_root.rglob("*.py"):
            if ".git" in path.parts or "logs" in path.parts:
                continue
            try:
                tree = ast.parse(path.read_text(encoding="utf-8"))
            except (OSError, SyntaxError, UnicodeDecodeError):
                continue
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    symbols.add(node.name)
        return symbols

    def _find_contract(self, path: Path, symbol: str) -> FunctionContract | None:
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (OSError, SyntaxError, UnicodeDecodeError):
            return None

        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == symbol:
                params = [arg.arg for arg in node.args.args]
                return_type = ast.unparse(node.returns) if node.returns else None
                return FunctionContract(
                    path=str(path.relative_to(self.repo_root)),
                    symbol=symbol,
                    parameters=params,
                    return_type=return_type,
                )
        return None
