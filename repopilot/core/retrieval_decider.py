from __future__ import annotations

import os

from repopilot.models.llm import RetrievalLLM, build_retrieval_prompt
from repopilot.schemas.retrieval import RetrievalDecision, RetrievalLevel
from repopilot.schemas.task import TaskSpec


class RetrievalDecider:
    HIGH_RISK_TASKS = {"bug_fix", "add_feature", "refactor", "add_test"}
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

        decision_reasons = payload.get("decision_reasons", [])
        if not isinstance(decision_reasons, list) or not all(
            isinstance(item, str) and item.strip() for item in decision_reasons
        ):
            decision_reasons = [reason.strip()]

        risk_level = payload.get("risk_level", "medium")
        if risk_level not in self.VALID_RISK_LEVELS:
            raise ValueError("risk_level must be low, medium, or high")

        confidence = payload.get("confidence", 0.8)
        if not isinstance(confidence, (int, float)):
            raise TypeError("confidence must be numeric")

        return RetrievalDecision(
            retrieval_level=normalized_level,
            search_targets=search_targets[:8],
            reason=reason.strip(),
            decision_reasons=decision_reasons[:5],
            risk_level=risk_level,
            confidence=float(confidence),
            summary="",
            source="llm",
            fallback_used=False,
        )

    def _heuristic_decision(self, task_spec: TaskSpec, fallback_used: bool) -> RetrievalDecision:
        targets = self._extract_targets(task_spec)
        has_concrete_target = bool(
            task_spec.target_files
            or task_spec.target_symbols
            or task_spec.scope_hint in {"symbol", "file", "module"}
        )
        scores = {
            RetrievalLevel.LIGHT: 0,
            RetrievalLevel.LOCAL: 0,
            RetrievalLevel.GLOBAL: 0,
        }
        decision_reasons: list[str] = []

        if task_spec.task_type in self.HIGH_RISK_TASKS:
            if has_concrete_target:
                scores[RetrievalLevel.LOCAL] += 2
                scores[RetrievalLevel.GLOBAL] += 1
                decision_reasons.append(
                    "High-risk modification task can start locally when the target is concrete."
                )
                decision_reasons.append(
                    "Retrieval should escalate to repository-wide context if local evidence is insufficient."
                )
            else:
                scores[RetrievalLevel.GLOBAL] += 3
                decision_reasons.append(
                    "High-risk modification task without a concrete target prefers repository-wide retrieval."
                )
        if task_spec.task_type == "doc_update":
            scores[RetrievalLevel.LIGHT] += 3
            decision_reasons.append("Documentation update with explicit targets can stay lightweight.")
        if task_spec.task_type == "explain_target":
            scores[RetrievalLevel.LOCAL] += 3
            decision_reasons.append("Targeted explanation should start from local retrieval.")
        if task_spec.scope_hint == "repo":
            scores[RetrievalLevel.GLOBAL] += 3
            decision_reasons.append("Task scope explicitly targets repository-level understanding.")
        if task_spec.scope_hint in {"symbol", "file", "module"}:
            scores[RetrievalLevel.LOCAL] += 2
            decision_reasons.append("Task has a concrete target that supports local retrieval first.")
        if task_spec.target_files:
            scores[RetrievalLevel.LOCAL] += 2
            decision_reasons.append("Explicit target files were extracted from the task.")
        if task_spec.target_symbols:
            scores[RetrievalLevel.LOCAL] += 2
            decision_reasons.append("Explicit target symbols were extracted from the task.")
        if task_spec.task_type == "explain_repo" and task_spec.scope_hint == "unknown":
            scores[RetrievalLevel.LIGHT] += 2
            decision_reasons.append("Explain-style task with no concrete target can start with lightweight retrieval.")
        if not task_spec.target_files and not task_spec.target_symbols and task_spec.task_type != "explain_repo":
            scores[RetrievalLevel.GLOBAL] += 1
            decision_reasons.append("Missing concrete targets increases the need for wider retrieval.")

        retrieval_level = max(scores, key=scores.get)
        confidence = min(0.95, 0.45 + 0.1 * scores[retrieval_level])
        if task_spec.task_type in self.HIGH_RISK_TASKS:
            risk_level = "high" if retrieval_level == RetrievalLevel.GLOBAL else "medium"
        else:
            risk_level = "high" if retrieval_level == RetrievalLevel.GLOBAL else "low"
        if retrieval_level == RetrievalLevel.GLOBAL:
            reason = "Task requires repository-wide retrieval before validation."
        elif retrieval_level == RetrievalLevel.LOCAL:
            reason = "Task can start with targeted local retrieval before validation."
        else:
            reason = "Task can start with lightweight retrieval and defer broader searches."

        summary = f"Retrieval decision: {retrieval_level.value} for {task_spec.task_type}."
        return RetrievalDecision(
            retrieval_level=retrieval_level,
            search_targets=targets,
            reason=reason,
            decision_reasons=decision_reasons[:5],
            risk_level=risk_level,
            confidence=confidence,
            summary=summary,
            source="heuristic",
            fallback_used=fallback_used,
        )

    def _extract_targets(self, task_spec: TaskSpec) -> list[str]:
        targets: list[str] = []
        cleaned_target = task_spec.target.strip()
        if cleaned_target:
            targets.append(cleaned_target)
        targets.extend(task_spec.target_files)
        targets.extend(task_spec.target_symbols)

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
