from __future__ import annotations

import ast
from pathlib import Path

from repopilot.schemas.repo_map import RepoMap, RepoNode


class RepoMapper:
    SUPPORTED_SUFFIXES = {".py", ".js", ".ts", ".tsx"}

    def __init__(self, repo_root: str) -> None:
        self.repo_root = Path(repo_root).resolve()

    def run(self) -> RepoMap:
        nodes: list[RepoNode] = []
        entrypoints: list[str] = []
        tests: list[str] = []

        for path in sorted(self.repo_root.rglob("*")):
            if not path.is_file():
                continue
            if ".git" in path.parts or "logs" in path.parts:
                continue
            if path.suffix not in self.SUPPORTED_SUFFIXES:
                continue

            rel = str(path.relative_to(self.repo_root))
            node_type = self._classify_path(rel)
            symbols = self._extract_symbols(path) if path.suffix == ".py" else []
            summary = f"{node_type} file"
            nodes.append(
                RepoNode(
                    path=rel,
                    node_type=node_type,
                    summary=summary,
                    symbols=symbols[:10],
                )
            )
            if path.name in {"main.py", "app.py"} or rel.endswith("/main.py"):
                entrypoints.append(rel)
            if "test" in rel.lower():
                tests.append(rel)

        summary = (
            f"Mapped {len(nodes)} source files, found "
            f"{len(entrypoints)} entrypoints and {len(tests)} test files."
        )
        return RepoMap(
            root=str(self.repo_root),
            entrypoints=entrypoints,
            tests=tests,
            nodes=nodes,
            summary=summary,
        )

    def _classify_path(self, rel_path: str) -> str:
        lowered = rel_path.lower()
        if "test" in lowered:
            return "test"
        if "route" in lowered:
            return "route"
        if "service" in lowered:
            return "service"
        if "schema" in lowered or "model" in lowered:
            return "schema"
        if "tool" in lowered:
            return "tool"
        return "module"

    def _extract_symbols(self, path: Path) -> list[str]:
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (OSError, SyntaxError, UnicodeDecodeError):
            return []

        symbols: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                symbols.append(node.name)
        return symbols
