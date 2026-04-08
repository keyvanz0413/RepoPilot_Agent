from __future__ import annotations

import argparse
from dataclasses import asdict
import json
import os
from pathlib import Path
from uuid import uuid4

from repopilot.app.logging import JsonlLogger
from repopilot.app.orchestrator import Orchestrator
from repopilot.models.llm import EnvJSONRetrievalLLM
from repopilot.schemas.run_context import RunContext
from repopilot.schemas.task import TaskInput
from repopilot.tools.file_tools import FileTools
from repopilot.tools.git_tools import GitTools
from repopilot.tools.safety_guard import SafetyGuard
from repopilot.tools.search_tools import SearchTools
from repopilot.tools.test_runner import TestRunner
from repopilot.tools.tool_registry import ToolRegistry


def build_registry(repo_root: str) -> ToolRegistry:
    safety_guard = SafetyGuard(repo_root=repo_root)
    file_tools = FileTools(repo_root)
    git_tools = GitTools(repo_root)
    registry = ToolRegistry(safety_guard=safety_guard)
    registry.register("read_file", file_tools.read_file, read_only=True)
    registry.register("write_file", file_tools.write_file)
    registry.register("search_text", SearchTools(repo_root).search_text, read_only=True)
    registry.register("create_checkpoint", git_tools.create_checkpoint)
    registry.register("revert_checkpoint", git_tools.revert_checkpoint)
    registry.register("run_test", TestRunner(repo_root).run_test)
    return registry


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="RepoPilot minimal runtime")
    parser.add_argument("task", help="Task description")
    parser.add_argument(
        "--repo-root",
        default=".",
        help="Repository root path",
    )
    parser.add_argument(
        "--test-command",
        default="",
        help="Optional validation command, e.g. 'pytest -q'",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    repo_root = str(Path(args.repo_root).resolve())
    task_input = TaskInput(
        raw_text=args.task,
        repo_root=repo_root,
        test_command=args.test_command or None,
    )
    ctx = RunContext(run_id=str(uuid4()), task_input=task_input)
    registry = build_registry(repo_root)
    logger = JsonlLogger(Path(repo_root) / "logs")
    orchestrator = Orchestrator(registry, logger)
    if "REPOPILOT_RETRIEVAL_DECISION_JSON" in os.environ:
        orchestrator.retrieval_decider.llm = EnvJSONRetrievalLLM()
        orchestrator.retrieval_decider.mode = (
            os.environ.get("REPOPILOT_RETRIEVAL_MODE", "auto").lower()
        )
    result = orchestrator.run(ctx)
    print(json.dumps(asdict(result), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
