# RepoPilot

Repository-level coding agent runtime with a hybrid control model:

- a light state machine for governance
- dynamic retrieval inside the `RETRIEVE` stage
- structured planning contracts for `PLAN`
- executor routing in `ACT`
- explicit review and recovery in `VERIFY` and `RECOVER`

## Current Capabilities

RepoPilot currently supports four task lanes:

- `explain_repo` / `explain_target`: analysis-only path
- `doc_update`: managed documentation updates
- `add_test`: managed test-file updates
- `bug_fix` / `add_feature` / `refactor`: code-edit path with executor routing

In the current implementation, local Ollama `gemma4:26b` drives:

- retrieval decisions in `RETRIEVE`
- file-level code editing when `PLAN` selects the `codex` executor

## Run

```bash
python -m repopilot.app.main "analyze this repo" --repo-root .
```

By default, RepoPilot now tries to use a local Ollama model as its LLM driver. The default model is `gemma4:26b`.

```bash
REPOPILOT_OLLAMA_MODEL=gemma4:26b \
python -m repopilot.app.main "解释 state_machine" --repo-root .
```

Useful Ollama settings:

- `REPOPILOT_USE_OLLAMA=0` to disable the Ollama driver
- `REPOPILOT_OLLAMA_MODEL` to select the local model tag
- `REPOPILOT_OLLAMA_BASE_URL` to override `http://127.0.0.1:11434`
- `REPOPILOT_OLLAMA_TIMEOUT` to increase the request timeout in seconds
- `REPOPILOT_OLLAMA_TEMPERATURE` to tune generation determinism

Optional test command:

```bash
python -m repopilot.app.main "run validation" --repo-root . --test-command "pytest -q"
```

Optional retrieval decision override for local LLM-shape testing:

```bash
REPOPILOT_RETRIEVAL_DECISION_JSON='{"retrieval_level":"LOCAL","search_targets":["state_machine"],"reason":"Narrow explanation task","risk_level":"low"}' \
python -m repopilot.app.main "解释 state_machine" --repo-root .
```

Optional Codex-style edit executor override for local testing:

```bash
REPOPILOT_CODEX_EDIT_JSON='{"summary":"Applied Codex edit","edits":[{"path":"repopilot/app/state_machine.py","content":"...full file content..."}]}' \
python -m repopilot.app.main "update state_machine" --repo-root .
```

## Runtime Model

RepoPilot no longer runs as a dead fixed workflow. The outer runtime now uses coarse control states:

- `TASK_INTAKE`
- `RETRIEVE`
- `PLAN`
- `ACT`
- `VERIFY`
- `RECOVER`

The state machine governs safety, logging, recovery, and stage boundaries. Stage internals are responsible for dynamic behavior.

## Retrieval

`RETRIEVE` is now a stage-local loop instead of a hard-coded chain of tiny states.

- `LIGHT`: start with minimal context and avoid repo-wide mapping
- `LOCAL`: search and inspect a narrow target-specific slice first
- `GLOBAL`: build repository-wide context with `RepoMapper`

The retrieval stage can stop when context is sufficient or escalate from `LOCAL` to `GLOBAL` when local evidence is not enough.

## Planning And Execution

`PLAN` produces a structured execution contract:

- `plan_kind`
- `requires_edit`
- `executor_choice`
- `files_to_edit`
- `tests_to_run`
- `success_criteria`
- `approval_required`

`ACT` then routes execution through the chosen executor:

- `analysis`: no repository edits
- `builtin_doc`: managed documentation updates
- `builtin_test`: managed test-file updates
- `builtin_code`: conservative function-level patching
- `codex`: file-level code editing inside `allowed_files`

When Ollama is enabled, both retrieval decisions and `codex`-style file editing are driven by the local Ollama model.

## Validation

`VERIFY` checks that:

- edits stayed inside the approved file scope
- required tests ran when the plan selected them
- no-op results are only accepted for explicitly idempotent managed updates

`RECOVER` remains explicit so retries, rollback, and future approval gates stay outside the free-form agent loop.

Current recovery behavior supports:

- retrying the same executor once for retryable edit failures
- switching from `codex` to `builtin_code` when a safe function contract exists
- rolling back changed files and rebuilding the plan after a failed review

## Current Limits

- `builtin_code` is still conservative and mainly handles narrow function-level edits
- broader file-level code changes depend on the local Ollama executor path
- `RETRIEVE` is dynamic, but its tool set is still limited to local search, repo map, contract, and impact
