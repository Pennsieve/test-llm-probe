# test-llm-probe

A test app for **LLM access**, which is opt-in: an app gets the Pennsieve LLM
governor (`LLM_GOVERNOR_FUNCTION_NAME`) and its sidecar (`ANTHROPIC_BASE_URL`,
`localhost:8765`) only when its `app.yml` declares `runtime.llm: true`, as
this one does.

It asks Claude, through the sidecar, for a one-sentence summary of the files
in `INPUT_DIR`, and writes `OUTPUT_DIR/llm-result.json`:

- `llmAccess`: whether the step had `LLM_GOVERNOR_FUNCTION_NAME` and `ANTHROPIC_BASE_URL`
- `attempts`: each model asked and the answer (HTTP status, summary or error)
- `model`, `summary`, `ok`

If the node doesn't allow `MODEL`, it retries with a model the governor says
it allows (preferring Haiku). With `REQUIRE_LLM` (the default) the run fails
when there is no LLM access or no answer, so the run's status is the test.

| Parameter | Default | |
|---|---|---|
| `MODEL` | `us.anthropic.claude-haiku-4-5-20251001-v1:0` | The model to ask first |
| `REQUIRE_LLM` | `true` | Fail without LLM access or an answer |

Pair it with [test-ports-processor](https://github.com/Pennsieve/test-ports-processor): link its `summary` output to this app's `report` input.
