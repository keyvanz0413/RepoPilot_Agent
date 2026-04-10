from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Protocol

from repopilot.schemas.task import TaskSpec


@dataclass
class RetrievalPrompt:
    system: str
    user: str


class RetrievalLLM(Protocol):
    def decide_retrieval(self, prompt: RetrievalPrompt, task_spec: TaskSpec) -> dict:
        """Return a structured retrieval decision payload."""


class EnvJSONRetrievalLLM:
    """Reads a structured retrieval decision from environment for local testing."""

    ENV_VAR = "REPOPILOT_RETRIEVAL_DECISION_JSON"

    def decide_retrieval(self, prompt: RetrievalPrompt, task_spec: TaskSpec) -> dict:
        raw = os.environ.get(self.ENV_VAR, "").strip()
        if not raw:
            raise RuntimeError(f"{self.ENV_VAR} is not set")
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"{self.ENV_VAR} is not valid JSON") from exc
        if not isinstance(data, dict):
            raise RuntimeError(f"{self.ENV_VAR} must encode a JSON object")
        return data


def build_retrieval_prompt(task_spec: TaskSpec) -> RetrievalPrompt:
    system = (
        "You are deciding a retrieval level for a repository agent before contract validation. "
        "Prefer LOCAL for concrete file or symbol targets, GLOBAL for repository-wide understanding, "
        "and LIGHT only when broader retrieval can be safely deferred. "
        "Return JSON only."
    )
    user = (
        f"task_type: {task_spec.task_type}\n"
        f"target: {task_spec.target}\n"
        f"intent: {task_spec.intent}\n"
        f"target_files: {', '.join(task_spec.target_files) if task_spec.target_files else '(none)'}\n"
        f"target_symbols: {', '.join(task_spec.target_symbols) if task_spec.target_symbols else '(none)'}\n"
        f"scope_hint: {task_spec.scope_hint}\n"
        f"constraints: {', '.join(task_spec.constraints) if task_spec.constraints else '(none)'}"
    )
    return RetrievalPrompt(system=system, user=user)
