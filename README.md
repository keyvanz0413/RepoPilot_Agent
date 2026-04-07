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
- Extended states: `REVIEW`, `RECOVER`
