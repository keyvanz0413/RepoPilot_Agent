from __future__ import annotations

import ast
import re
from pathlib import Path

from repopilot.schemas.contract import CodeTarget, ContractReport, FunctionContract
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

    def run(self, task_spec: TaskSpec, candidate_files: list[str] | None = None) -> ContractReport:
        if task_spec.task_type in {"doc_update", "explain_target"} and task_spec.target_files:
            return self._validate_file_targets(task_spec, candidate_files)

        symbol = self._guess_symbol(task_spec)
        report = ContractReport(target=task_spec.target, matched_symbol=symbol)
        if not symbol:
            report.uncertainties.append("Could not infer target symbol from task text")
            report.summary = "No concrete symbol inferred for contract validation."
            return report

        preferred_paths = self._resolve_candidate_paths(candidate_files)
        for path in preferred_paths:
            contract = self._find_contract(path, symbol)
            if contract:
                rel = str(path.relative_to(self.repo_root))
                report.matched_files.append(rel)
                report.function_contracts.append(contract)
        report.searched_files = [str(path.relative_to(self.repo_root)) for path in preferred_paths]

        if not report.function_contracts:
            if task_spec.task_type in {"bug_fix", "add_feature", "refactor", "add_test"} and task_spec.target_files:
                return self._validate_code_file_targets(task_spec, report, candidate_files)
            if candidate_files:
                report.uncertainties.append(
                    "Symbol was not found in the restricted candidate file set"
                )
            report.uncertainties.append(f"Symbol '{symbol}' not found in Python source")
            report.summary = f"No Python function contract found for symbol '{symbol}'."
            return report

        report.summary = (
            f"Found {len(report.function_contracts)} contract match(es) for symbol '{symbol}'"
            f" after searching {len(report.searched_files)} file(s)."
        )
        return report

    def _validate_file_targets(
        self,
        task_spec: TaskSpec,
        candidate_files: list[str] | None = None,
    ) -> ContractReport:
        report = ContractReport(target=task_spec.target)
        candidate_set = set(candidate_files or task_spec.target_files)
        matched_files: list[str] = []
        searched_files: list[str] = []

        for rel_path in task_spec.target_files:
            path = (self.repo_root / rel_path).resolve()
            if not path.exists():
                report.uncertainties.append(f"Target file does not exist: {rel_path}")
                continue
            try:
                path.relative_to(self.repo_root)
            except ValueError:
                report.uncertainties.append(f"Target file is outside repo root: {rel_path}")
                continue
            if candidate_set and rel_path not in candidate_set:
                continue
            searched_files.append(rel_path)
            matched_files.append(rel_path)

        report.matched_files = matched_files
        report.searched_files = searched_files
        report.matched_symbol = task_spec.target_symbols[0] if task_spec.target_symbols else None
        if matched_files:
            report.summary = (
                f"Validated {len(matched_files)} explicit target file(s) for {task_spec.task_type}."
            )
        else:
            report.summary = "No explicit target files could be validated."
        return report

    def _validate_code_file_targets(
        self,
        task_spec: TaskSpec,
        report: ContractReport,
        candidate_files: list[str] | None = None,
    ) -> ContractReport:
        candidate_set = set(candidate_files or task_spec.target_files)
        matched_files: list[str] = []

        for rel_path in task_spec.target_files:
            path = (self.repo_root / rel_path).resolve()
            if not path.exists() or path.suffix != ".py":
                continue
            try:
                path.relative_to(self.repo_root)
            except ValueError:
                continue
            if candidate_set and rel_path not in candidate_set:
                continue
            matched_files.append(rel_path)

        if matched_files:
            report.matched_files = matched_files
            report.code_targets = [
                CodeTarget(path=rel_path, target_kind="file", symbol=report.matched_symbol)
                for rel_path in matched_files
            ]
            report.summary = (
                f"Validated {len(matched_files)} file-level code target(s) for {task_spec.task_type}."
            )
            report.uncertainties.append(
                "No function contract was found, so the workflow fell back to file-level code targets."
            )
            return report

        if candidate_files:
            report.uncertainties.append("Symbol was not found in the restricted candidate file set")
        report.uncertainties.append(f"Symbol '{report.matched_symbol}' not found in Python source")
        report.summary = f"No Python function contract found for symbol '{report.matched_symbol}'."
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
        for path in self._iter_python_files():
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

    def _iter_python_files(self) -> list[Path]:
        paths: list[Path] = []
        for path in sorted(self.repo_root.rglob("*.py")):
            if ".git" in path.parts or "logs" in path.parts:
                continue
            paths.append(path)
        return paths

    def _resolve_candidate_paths(self, candidate_files: list[str] | None) -> list[Path]:
        if not candidate_files:
            return self._iter_python_files()

        resolved: list[Path] = []
        seen: set[Path] = set()
        for rel_path in candidate_files:
            path = (self.repo_root / rel_path).resolve()
            if path.suffix != ".py" or not path.exists():
                continue
            try:
                path.relative_to(self.repo_root)
            except ValueError:
                continue
            if path in seen:
                continue
            seen.add(path)
            resolved.append(path)
        return resolved or self._iter_python_files()
