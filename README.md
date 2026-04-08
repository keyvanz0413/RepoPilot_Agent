# RepoPilot

Minimal first-step runtime skeleton for a repository-level coding agent.

## Run

```bash
python -m repopilot.app.main "analyze this repo" --repo-root .
```

Optional test command:

```bash
python -m repopilot.app.main "run validation" --repo-root . --test-command "pytest -q"
```

Optional retrieval decision override for local LLM-shape testing:

```bash
REPOPILOT_RETRIEVAL_DECISION_JSON='{"retrieval_level":"LOCAL","search_targets":["state_machine"],"reason":"Narrow explanation task","risk_level":"low"}' \
python -m repopilot.app.main "解释 state_machine" --repo-root .
```

## Retrieval Flow

RepoPilot now uses three retrieval levels:

- `LIGHT`: skip explicit retrieval and move directly to contract validation
- `LOCAL`: run `LOCAL_RETRIEVE` to search a few target-specific queries and inspect a few matched files
- `GLOBAL`: run `MAP_REPO` to build repository-wide structure context

Current escalation path:

```text
DECIDE_RETRIEVAL
  -> LIGHT -> VALIDATE_CONTRACT
  -> LOCAL -> LOCAL_RETRIEVE -> VALIDATE_CONTRACT
                  insufficient context
                  -> ESCALATE_RETRIEVAL -> MAP_REPO -> VALIDATE_CONTRACT
  -> GLOBAL -> MAP_REPO -> VALIDATE_CONTRACT
```

`VALIDATE_CONTRACT` and `ANALYZE_IMPACT` now consume retrieval outputs as candidate file scopes instead of silently widening to repo-wide search inside the same node.

## Included in step one

- `RunContext`
- `StateMachine`
- `Orchestrator`
- `ToolRegistry`
- `SafetyGuard`
- Basic tools: `read_file`, `search_text`, `create_checkpoint`, `run_test`

## Included in step two

- `RepoMapper`
- `ContractValidator`
- `ImpactAnalyzer`
- Extended states: `MAP_REPO`, `VALIDATE_CONTRACT`, `ANALYZE_IMPACT`

## Included in step three

- `Planner`
- Conservative `Coder`
- `Reviewer`
- `RecoveryManager`
- `RetrievalDecider`
- `LocalRetriever`
- Extended states: `DECIDE_RETRIEVAL`, `LOCAL_RETRIEVE`, `ESCALATE_RETRIEVAL`, `REVIEW`, `RECOVER`
