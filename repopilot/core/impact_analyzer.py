from __future__ import annotations

from pathlib import Path

from repopilot.schemas.contract import ContractReport
from repopilot.schemas.impact import ImpactReport, SymbolReference


class ImpactAnalyzer:
    def __init__(self, repo_root: str) -> None:
        self.repo_root = Path(repo_root).resolve()

    def run(self, contract_report: ContractReport) -> ImpactReport:
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

        for path in sorted(self.repo_root.rglob("*")):
            if not path.is_file():
                continue
            if ".git" in path.parts or "logs" in path.parts:
                continue
            if path.suffix not in {".py", ".js", ".ts", ".tsx"}:
                continue

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
            f"Found {reference_count} reference(s) across {len(report.affected_files)} file(s)."
        )
        return report
