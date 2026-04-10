from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib import error, request

from repopilot.models.codex import CodexExecutor
from repopilot.models.llm import RetrievalLLM, RetrievalPrompt
from repopilot.schemas.edit import CodexEditRequest, ProposedFileEdit
from repopilot.schemas.task import TaskSpec


@dataclass
class OllamaConfig:
    base_url: str = "http://127.0.0.1:11434"
    model: str = "gemma4:26b"
    temperature: float = 0.0
    timeout_seconds: float = 120.0

    @classmethod
    def from_env(cls) -> "OllamaConfig":
        temperature_raw = os.environ.get("REPOPILOT_OLLAMA_TEMPERATURE", "0")
        timeout_raw = os.environ.get("REPOPILOT_OLLAMA_TIMEOUT", "120")
        try:
            temperature = float(temperature_raw)
        except ValueError:
            temperature = 0.0
        try:
            timeout_seconds = float(timeout_raw)
        except ValueError:
            timeout_seconds = 120.0
        return cls(
            base_url=os.environ.get("REPOPILOT_OLLAMA_BASE_URL", "http://127.0.0.1:11434"),
            model=os.environ.get("REPOPILOT_OLLAMA_MODEL", "gemma4:26b"),
            temperature=temperature,
            timeout_seconds=timeout_seconds,
        )


class OllamaClient:
    def __init__(self, config: OllamaConfig) -> None:
        self.config = config

    def chat_json(self, messages: list[dict[str, str]], schema: dict[str, Any]) -> dict[str, Any]:
        payload = {
            "model": self.config.model,
            "messages": messages,
            "stream": False,
            "format": schema,
            "options": {
                "temperature": self.config.temperature,
            },
        }
        url = f"{self.config.base_url.rstrip('/')}/api/chat"
        req = request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with request.urlopen(req, timeout=self.config.timeout_seconds) as response:
                body = response.read().decode("utf-8")
        except error.URLError as exc:
            raise RuntimeError(f"Failed to reach Ollama at {url}") from exc
        except OSError as exc:
            raise RuntimeError("Failed to read the Ollama response") from exc

        try:
            data = json.loads(body)
        except json.JSONDecodeError as exc:
            raise RuntimeError("Ollama returned invalid JSON") from exc

        message = data.get("message", {})
        if not isinstance(message, dict):
            raise RuntimeError("Ollama response did not include a valid message object")
        content = message.get("content", "")
        if not isinstance(content, str) or not content.strip():
            raise RuntimeError("Ollama response did not include structured content")

        try:
            parsed = json.loads(content)
        except json.JSONDecodeError:
            parsed = self._extract_json_object(content)
        if not isinstance(parsed, dict):
            raise RuntimeError("Ollama structured output must be a JSON object")
        return parsed

    def _extract_json_object(self, content: str) -> dict[str, Any]:
        cleaned = content.strip()
        if cleaned.startswith("```"):
            lines = cleaned.splitlines()
            if lines and lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].startswith("```"):
                lines = lines[:-1]
            cleaned = "\n".join(lines).strip()

        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise RuntimeError("Ollama message content was not valid JSON")

        candidate = cleaned[start : end + 1]
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError as exc:
            raise RuntimeError("Ollama message content was not valid JSON") from exc
        if not isinstance(parsed, dict):
            raise RuntimeError("Ollama structured output must be a JSON object")
        return parsed


class OllamaRetrievalLLM:
    SCHEMA = {
        "type": "object",
        "properties": {
            "retrieval_level": {"type": "string", "enum": ["LIGHT", "LOCAL", "GLOBAL"]},
            "search_targets": {
                "type": "array",
                "items": {"type": "string"},
            },
            "reason": {"type": "string"},
            "decision_reasons": {
                "type": "array",
                "items": {"type": "string"},
            },
            "risk_level": {"type": "string", "enum": ["low", "medium", "high"]},
            "confidence": {"type": "number"},
        },
        "required": ["retrieval_level", "search_targets", "reason", "risk_level"],
    }

    def __init__(self, config: OllamaConfig | None = None) -> None:
        self.config = config or OllamaConfig.from_env()
        self.client = OllamaClient(self.config)

    def decide_retrieval(self, prompt: RetrievalPrompt, task_spec: TaskSpec) -> dict:
        schema_text = json.dumps(self.SCHEMA, ensure_ascii=False)
        messages = [
            {
                "role": "system",
                "content": (
                    f"{prompt.system}\n"
                    "Return only JSON that matches this schema:\n"
                    f"{schema_text}"
                ),
            },
            {
                "role": "user",
                "content": prompt.user,
            },
        ]
        return self.client.chat_json(messages, self.SCHEMA)


class OllamaCodexExecutor:
    SCHEMA = {
        "type": "object",
        "properties": {
            "summary": {"type": "string"},
            "edits": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string"},
                        "content": {"type": "string"},
                        "rationale": {"type": "string"},
                    },
                    "required": ["path", "content"],
                },
            },
        },
        "required": ["summary", "edits"],
    }

    def __init__(self, config: OllamaConfig | None = None) -> None:
        self.config = config or OllamaConfig.from_env()
        self.client = OllamaClient(self.config)

    def edit(self, request_obj: CodexEditRequest) -> tuple[list[ProposedFileEdit], str]:
        schema_text = json.dumps(self.SCHEMA, ensure_ascii=False)
        messages = [
            {
                "role": "system",
                "content": (
                    "You are the file-editing model for RepoPilot. "
                    "Only edit files listed in allowed_files. "
                    "Return only JSON that matches the provided schema. "
                    "Each edit must contain the full replacement content for that file.\n"
                    f"Schema:\n{schema_text}"
                ),
            },
            {
                "role": "user",
                "content": self._build_edit_prompt(request_obj),
            },
        ]
        payload = self.client.chat_json(messages, self.SCHEMA)
        summary = payload.get("summary", "Ollama executor proposed edits.")
        if not isinstance(summary, str):
            raise RuntimeError("Ollama edit summary must be a string")

        edits_raw = payload.get("edits", [])
        if not isinstance(edits_raw, list):
            raise RuntimeError("Ollama edits must be a list")

        edits: list[ProposedFileEdit] = []
        for item in edits_raw:
            if not isinstance(item, dict):
                raise RuntimeError("Each Ollama edit must be an object")
            path = item.get("path")
            content = item.get("content")
            rationale = item.get("rationale", "")
            if not isinstance(path, str) or not path.strip():
                raise RuntimeError("Ollama edit.path must be a non-empty string")
            if not isinstance(content, str):
                raise RuntimeError("Ollama edit.content must be a string")
            if not isinstance(rationale, str):
                raise RuntimeError("Ollama edit.rationale must be a string")
            edits.append(ProposedFileEdit(path=path, content=content, rationale=rationale))
        return edits, summary

    def _build_edit_prompt(self, request_obj: CodexEditRequest) -> str:
        file_sections: list[str] = []
        repo_root = Path(request_obj.repo_root)
        for rel_path in request_obj.allowed_files:
            full_path = repo_root / rel_path
            try:
                content = full_path.read_text(encoding="utf-8")
            except OSError:
                content = ""
            file_sections.append(
                "\n".join(
                    [
                        f"FILE: {rel_path}",
                        "CONTENT-BEGIN",
                        content,
                        "CONTENT-END",
                    ]
                )
            )

        reference_lines = [
            f"- {snippet.path}:{snippet.line}: {snippet.text}"
            for snippet in request_obj.reference_snippets
        ]
        instructions = [
            f"goal: {request_obj.goal}",
            f"task_type: {request_obj.task_type}",
            f"allowed_files: {', '.join(request_obj.allowed_files) if request_obj.allowed_files else '(none)'}",
            f"required_tests: {', '.join(request_obj.required_tests) if request_obj.required_tests else '(none)'}",
            f"constraints: {', '.join(request_obj.constraints) if request_obj.constraints else '(none)'}",
            f"repo_instructions: {' | '.join(request_obj.repo_instructions) if request_obj.repo_instructions else '(none)'}",
            f"editing_rules: {' | '.join(request_obj.editing_rules) if request_obj.editing_rules else '(none)'}",
            f"testing_rules: {' | '.join(request_obj.testing_rules) if request_obj.testing_rules else '(none)'}",
            f"plan_steps: {' | '.join(request_obj.plan_steps) if request_obj.plan_steps else '(none)'}",
            f"retrieval_summary: {request_obj.retrieval_summary or '(none)'}",
            f"contract_summary: {request_obj.contract_summary or '(none)'}",
            f"impact_summary: {request_obj.impact_summary or '(none)'}",
            f"plan_summary: {request_obj.plan_summary or '(none)'}",
            f"target_symbol: {request_obj.target_symbol or '(none)'}",
            f"contract_files: {', '.join(request_obj.contract_files) if request_obj.contract_files else '(none)'}",
            f"impact_files: {', '.join(request_obj.impact_files) if request_obj.impact_files else '(none)'}",
            "reference_snippets:",
            *(reference_lines or ["- (none)"]),
            "Return edits only for files that must change.",
            "Do not include explanations outside the JSON output.",
            "Use full file content for each edited file.",
        ]
        if file_sections:
            instructions.extend(["allowed_file_contents:"] + file_sections)
        return "\n".join(instructions)
