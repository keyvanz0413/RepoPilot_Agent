from __future__ import annotations

from pathlib import Path

from repopilot.schemas.local_retrieval import LocalRetrievalReport, RetrievalSnippet
from repopilot.schemas.retrieval import RetrievalDecision
from repopilot.tools.tool_registry import ToolRegistry


class LocalRetriever:
    def __init__(self, tool_registry: ToolRegistry, repo_root: str) -> None:
        self.tool_registry = tool_registry
        self.repo_root = Path(repo_root).resolve()

    def run(self, decision: RetrievalDecision) -> LocalRetrievalReport:
        report = LocalRetrievalReport(queries=list(decision.search_targets[:3]))
        matched_files: list[str] = []

        for query in report.queries:
            result = self.tool_registry.run("search_text", query=query)
            if not result.ok:
                continue
            self._collect_matches(result.data.get("stdout", ""), matched_files, report)

        report.matched_files = matched_files[:10]
        for rel_path in report.matched_files[:3]:
            read_result = self.tool_registry.run("read_file", path=str(self.repo_root / rel_path))
            if read_result.ok:
                report.inspected_files.append(rel_path)

        report.summary = (
            f"Local retrieval ran {len(report.queries)} querie(s), found "
            f"{len(report.matched_files)} file(s) and inspected {len(report.inspected_files)} file(s)."
        )
        return report

    def _collect_matches(
        self,
        stdout: str,
        matched_files: list[str],
        report: LocalRetrievalReport,
    ) -> None:
        for raw_line in stdout.splitlines():
            parts = raw_line.split(":", 2)
            if len(parts) != 3:
                continue
            path_str, line_str, text = parts
            rel_path = self._to_relative_path(path_str)
            if rel_path is None:
                continue
            if rel_path not in matched_files:
                matched_files.append(rel_path)
            if len(report.snippets) >= 12:
                continue
            try:
                line_no = int(line_str)
            except ValueError:
                line_no = 0
            report.snippets.append(RetrievalSnippet(path=rel_path, line=line_no, text=text.strip()))

    def _to_relative_path(self, raw_path: str) -> str | None:
        path = Path(raw_path)
        try:
            return str(path.resolve().relative_to(self.repo_root))
        except ValueError:
            return None
