from __future__ import annotations

import json
import os
from typing import Protocol

from repopilot.schemas.edit import CodexEditRequest, ProposedFileEdit


class CodexExecutor(Protocol):
    def edit(self, request: CodexEditRequest) -> tuple[list[ProposedFileEdit], str]:
        """Return proposed file edits and a summary."""


class EnvJSONCodexExecutor:
    """Reads Codex-style edit proposals from environment for local integration testing."""

    ENV_VAR = "REPOPILOT_CODEX_EDIT_JSON"

    def edit(self, request: CodexEditRequest) -> tuple[list[ProposedFileEdit], str]:
        raw = os.environ.get(self.ENV_VAR, "").strip()
        if not raw:
            raise RuntimeError(f"{self.ENV_VAR} is not set")
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"{self.ENV_VAR} is not valid JSON") from exc
        if not isinstance(data, dict):
            raise RuntimeError(f"{self.ENV_VAR} must encode a JSON object")

        edits_raw = data.get("edits", [])
        if not isinstance(edits_raw, list):
            raise RuntimeError("edits must be a list")

        edits: list[ProposedFileEdit] = []
        for item in edits_raw:
            if not isinstance(item, dict):
                raise RuntimeError("each edit must be an object")
            path = item.get("path")
            content = item.get("content")
            rationale = item.get("rationale", "")
            if not isinstance(path, str) or not path.strip():
                raise RuntimeError("edit.path must be a non-empty string")
            if not isinstance(content, str):
                raise RuntimeError("edit.content must be a string")
            if not isinstance(rationale, str):
                raise RuntimeError("edit.rationale must be a string")
            edits.append(ProposedFileEdit(path=path, content=content, rationale=rationale))

        summary = data.get("summary", "Codex executor proposed edits.")
        if not isinstance(summary, str):
            raise RuntimeError("summary must be a string")
        return edits, summary
