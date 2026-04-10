from __future__ import annotations

from pathlib import Path

from repopilot.schemas.contract import ContractReport
from repopilot.schemas.impact import ImpactReport, SymbolReference
from repopilot.schemas.task import TaskSpec


class ImpactAnalyzer:
    def __init__(self, repo_root: str) -> None:
        self.repo_root = Path(repo_root).resolve()

    def run(
        self,
        contract_report: ContractReport,
        candidate_files: list[str] | None = None,
        task_spec: TaskSpec | None = None,
    ) -> ImpactReport:
        if task_spec and task_spec.task_type == "doc_update":
            return self._analyze_doc_impact(contract_report)
        if task_spec and task_spec.task_type == "explain_target" and contract_report.matched_files:
            return self._analyze_file_reference_impact(contract_report, candidate_files)

        symbol = contract_report.matched_symbol
        report = ImpactReport(target=contract_report.target, matched_symbol=symbol)
        if not symbol:
            report.risk_level = "medium"
            report.impact_reasons.append("No symbol identified, impact cannot be narrowed")
            report.summary = "Impact analysis is inconclusive without a target symbol."
            return report

        refs: list[SymbolReference] = []
        affected_files: set[str] = set()
        related_tests: set[str] = set()

        paths_to_scan = self._resolve_candidate_paths(candidate_files)
        report.searched_files = [str(path.relative_to(self.repo_root)) for path in paths_to_scan]

        for path in paths_to_scan:

            rel = str(path.relative_to(self.repo_root))
            try:
                lines = path.read_text(encoding="utf-8").splitlines()
            except (OSError, UnicodeDecodeError):
                continue

            for idx, line in enumerate(lines, start=1):
                if symbol not in line:
                    continue
                refs.append(SymbolReference(path=rel, line=idx, text=line.strip()))
                affected_files.add(rel)
                if "test" in rel.lower():
                    related_tests.add(rel)

        report.references = refs[:50]
        report.affected_files = sorted(affected_files)
        report.related_tests = sorted(related_tests)
        reference_count = len(report.references)

        if reference_count > 10:
            report.risk_level = "high"
        elif reference_count > 3:
            report.risk_level = "medium"
        else:
            report.risk_level = "low"

        if contract_report.function_contracts:
            report.impact_reasons.append("Function contract exists and may have callers")
        if report.related_tests:
            report.impact_reasons.append("Related test files mention the target symbol")
        if not report.affected_files:
            if candidate_files:
                report.impact_reasons.append("Restricted candidate file set produced no references")
            report.impact_reasons.append("No references found outside contract search")
        elif not report.related_tests:
            for path in report.affected_files:
                stem = Path(path).stem
                candidate_tests = list(self.repo_root.rglob(f"test*{stem}*.py"))
                for test_path in candidate_tests:
                    rel = str(test_path.relative_to(self.repo_root))
                    related_tests.add(rel)
            report.related_tests = sorted(related_tests)
            if report.related_tests:
                report.impact_reasons.append("Matched likely test files by affected module names")

        report.summary = (
            f"Found {reference_count} reference(s) across {len(report.affected_files)} file(s)"
            f" after searching {len(report.searched_files)} file(s)."
        )
        return report

    def _analyze_doc_impact(self, contract_report: ContractReport) -> ImpactReport:
        report = ImpactReport(
            target=contract_report.target,
            matched_symbol=contract_report.matched_symbol,
            risk_level="low",
            searched_files=list(contract_report.matched_files),
            affected_files=list(contract_report.matched_files),
        )
        report.impact_reasons.append("Documentation tasks stay file-scoped unless later steps require more.")
        report.summary = (
            f"Kept impact analysis scoped to {len(report.affected_files)} explicit documentation file(s)."
        )
        return report

    def _analyze_file_reference_impact(
        self,
        contract_report: ContractReport,
        candidate_files: list[str] | None,
    ) -> ImpactReport:
        report = ImpactReport(target=contract_report.target, matched_symbol=contract_report.matched_symbol)
        target_paths = list(contract_report.matched_files)
        target_tokens = {Path(path).name for path in target_paths}
        target_tokens.update(path for path in target_paths)

        refs: list[SymbolReference] = []
        affected_files: set[str] = set()
        paths_to_scan = self._resolve_candidate_paths(candidate_files)
        report.searched_files = [str(path.relative_to(self.repo_root)) for path in paths_to_scan]

        for path in paths_to_scan:
            rel = str(path.relative_to(self.repo_root))
            if rel in target_paths:
                continue
            try:
                lines = path.read_text(encoding="utf-8").splitlines()
            except (OSError, UnicodeDecodeError):
                continue
            for idx, line in enumerate(lines, start=1):
                if not any(token in line for token in target_tokens):
                    continue
                refs.append(SymbolReference(path=rel, line=idx, text=line.strip()))
                affected_files.add(rel)

        report.references = refs[:50]
        report.affected_files = sorted(affected_files)
        report.risk_level = "low" if len(report.references) <= 5 else "medium"
        if report.affected_files:
            report.impact_reasons.append("Found references to the explicit target file in related source files.")
        else:
            report.impact_reasons.append("No source references to the explicit target file were found.")
        report.summary = (
            f"Found {len(report.references)} file reference(s) across {len(report.affected_files)} file(s)"
            f" after searching {len(report.searched_files)} file(s)."
        )
        return report

    def _iter_source_files(self) -> list[Path]:
        paths: list[Path] = []
        for path in sorted(self.repo_root.rglob("*")):
            if not path.is_file():
                continue
            if ".git" in path.parts or "logs" in path.parts:
                continue
            if path.suffix not in {".py", ".js", ".ts", ".tsx"}:
                continue
            paths.append(path)
        return paths

    def _resolve_candidate_paths(self, candidate_files: list[str] | None) -> list[Path]:
        if not candidate_files:
            return self._iter_source_files()

        resolved: list[Path] = []
        seen: set[Path] = set()
        for rel_path in candidate_files:
            path = (self.repo_root / rel_path).resolve()
            if path.suffix not in {".py", ".js", ".ts", ".tsx"} or not path.exists():
                continue
            try:
                path.relative_to(self.repo_root)
            except ValueError:
                continue
            if path in seen:
                continue
            seen.add(path)
            resolved.append(path)
        return resolved or self._iter_source_files()
