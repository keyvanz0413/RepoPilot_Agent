from __future__ import annotations

import os

from repopilot.models.llm import RetrievalLLM, build_retrieval_prompt
from repopilot.schemas.retrieval import RetrievalDecision, RetrievalLevel
from repopilot.schemas.task import TaskSpec


class RetrievalDecider:
    HIGH_RISK_TASKS = {"bug_fix", "add_feature", "refactor"}
    VALID_RISK_LEVELS = {"low", "medium", "high"}

    def __init__(self, llm: RetrievalLLM | None = None, mode: str | None = None) -> None:
        self.llm = llm
        self.mode = (mode or os.environ.get("REPOPILOT_RETRIEVAL_MODE") or "heuristic").lower()

    def run(self, task_spec: TaskSpec) -> RetrievalDecision:
        if self.mode in {"llm", "auto"} and self.llm is not None:
            llm_result = self._run_llm(task_spec)
            if llm_result is not None:
                return llm_result
            if self.mode == "llm":
                return self._heuristic_decision(task_spec, fallback_used=True)
        return self._heuristic_decision(task_spec, fallback_used=False)

    def _run_llm(self, task_spec: TaskSpec) -> RetrievalDecision | None:
        prompt = build_retrieval_prompt(task_spec)
        try:
            payload = self.llm.decide_retrieval(prompt, task_spec)
        except RuntimeError:
            return None

        try:
            decision = self._normalize_llm_payload(payload, task_spec)
        except (TypeError, ValueError):
            return None
        decision.summary = (
            f"Retrieval decision: {decision.retrieval_level.value} for {task_spec.task_type}."
        )
        decision.source = "llm"
        return decision

    def _normalize_llm_payload(self, payload: dict, task_spec: TaskSpec) -> RetrievalDecision:
        retrieval_level = payload.get("retrieval_level")
        if not isinstance(retrieval_level, str):
            raise TypeError("retrieval_level must be a string")
        try:
            normalized_level = RetrievalLevel(retrieval_level.upper())
        except ValueError as exc:
            raise ValueError("retrieval_level must be LIGHT, LOCAL, or GLOBAL") from exc

        search_targets = payload.get("search_targets", [])
        if not isinstance(search_targets, list) or not all(
            isinstance(item, str) and item.strip() for item in search_targets
        ):
            raise TypeError("search_targets must be a list of non-empty strings")

        reason = payload.get("reason", "")
        if not isinstance(reason, str) or not reason.strip():
            raise TypeError("reason must be a non-empty string")

        risk_level = payload.get("risk_level", "medium")
        if risk_level not in self.VALID_RISK_LEVELS:
            raise ValueError("risk_level must be low, medium, or high")

        return RetrievalDecision(
            retrieval_level=normalized_level,
            search_targets=search_targets[:8],
            reason=reason.strip(),
            risk_level=risk_level,
            summary="",
            source="llm",
            fallback_used=False,
        )

    def _heuristic_decision(self, task_spec: TaskSpec, fallback_used: bool) -> RetrievalDecision:
        intent = task_spec.intent.lower()
        targets = self._extract_targets(task_spec)

        mentions_repo = "repo" in intent or "仓库" in task_spec.intent or "代码库" in task_spec.intent
        mentions_specific_target = any(
            marker in task_spec.intent for marker in ("`", "/", ".", "_")
        ) or len(targets) > 1

        if task_spec.task_type in self.HIGH_RISK_TASKS or mentions_repo:
            retrieval_level = RetrievalLevel.GLOBAL
            risk_level = "high"
            reason = "Task is broad or high risk, so repository-wide mapping should run first."
        elif task_spec.task_type == "explain_repo" and mentions_specific_target:
            retrieval_level = RetrievalLevel.LOCAL
            risk_level = "low"
            reason = "Task is narrow and target-specific, so local retrieval is enough before validation."
        else:
            retrieval_level = RetrievalLevel.LIGHT
            risk_level = "low"
            reason = "Task appears simple enough to start with lightweight retrieval only."

        summary = f"Retrieval decision: {retrieval_level.value} for {task_spec.task_type}."
        return RetrievalDecision(
            retrieval_level=retrieval_level,
            search_targets=targets,
            reason=reason,
            risk_level=risk_level,
            summary=summary,
            source="heuristic",
            fallback_used=fallback_used,
        )

    def _extract_targets(self, task_spec: TaskSpec) -> list[str]:
        targets: list[str] = []
        cleaned_target = task_spec.target.strip()
        if cleaned_target:
            targets.append(cleaned_target)

        for token in task_spec.intent.replace("`", " ").split():
            normalized = token.strip(".,:;()[]{}")
            if not normalized:
                continue
            if "/" in normalized or "." in normalized or "_" in normalized:
                targets.append(normalized)

        deduped: list[str] = []
        seen: set[str] = set()
        for target in targets:
            if target in seen:
                continue
            seen.add(target)
            deduped.append(target)
        return deduped[:8]
