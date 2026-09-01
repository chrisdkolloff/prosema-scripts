# Assistant eval harness

Offline scoring of how reliably a model turns German questions into the right
catalogue tool calls. It drives `service.ask` against the **current complete
article snapshot** — no UI. Not a pytest test: it talks to a model and
**consumes tokens** (prompt + completion) on every question.

```bash
# from the repo root, with .env loaded the usual way
python tests/eval/run_eval.py --provider openai_compatible --model qwen2.5-7b-instruct
python tests/eval/run_eval.py --provider azure --model gpt-4o
python tests/eval/run_eval.py --id count-all          # one question, cheap iteration
python tests/eval/run_eval.py --limit 1               # first N questions
```

Each run prints a markdown table (pass/fail per criterion, then totals) and
writes the same text to `tests/eval/results/<UTC-timestamp>.md`. Failure rows
are followed by the question, the tool calls, the filter, and the German
answer. Passing questions stay as table rows only.

The harness force-enables the assistant for the process and writes
`assistant_queries` audit rows (user `eval-harness`) like the UI would.

## Point it at LM Studio (openai_compatible)

LM Studio’s local server is an OpenAI-compatible `/v1` endpoint. Typical
defaults:

```bash
# .env (or export) — the runner uses this URL if ASSISTANT_BASE_URL is unset
ASSISTANT_PROVIDER=openai_compatible
ASSISTANT_BASE_URL=http://127.0.0.1:1234/v1
ASSISTANT_MODEL=qwen2.5-7b-instruct   # whatever LM Studio shows as the loaded model
ASSISTANT_TIMEOUT_SECONDS=120         # local models are slower than Azure
```

Then:

```bash
python tests/eval/run_eval.py --provider openai_compatible --model qwen2.5-7b-instruct
```

`--model` is sent as the request `model` field. If `ASSISTANT_BASE_URL` is
empty, the runner falls back to `http://127.0.0.1:1234/v1`. Load a model in
LM Studio and start the local server before running.

The openai_compatible path does **not** use native tool-calling; the
assistant asks the model for a JSON `{tool, args}` / `{answer}` object.

## Point it at Azure OpenAI

```bash
# .env
ASSISTANT_PROVIDER=azure
AZURE_OPENAI_ENDPOINT=https://<resource>.openai.azure.com
AZURE_OPENAI_DEPLOYMENT=gpt-4o
AZURE_OPENAI_API_VERSION=2024-10-21
```

Auth is `DefaultAzureCredential` (same as the app: `az login` locally). Then:

```bash
python tests/eval/run_eval.py --provider azure --model gpt-4o
```

On Azure, `--model` is the **deployment name** (it also sets
`AZURE_OPENAI_DEPLOYMENT` for this process). Routing is by deployment, not by
a free-form model string.

## Snapshot dependence

Scores are only meaningful against the snapshot that was current at run time.
A new weclapp pull changes row counts and can change which filter is “right”.
Every result file records:

- `snapshot_id`
- `provider` / `model`
- `prompt_tokens` / `completion_tokens` / `total_tokens`

Do not compare a result file from last week to today’s snapshot without
re-running. `min_rows` / `max_rows` in `questions.yaml` are optional and
should be measured on the snapshot you care about.

## Adding a question

1. Copy an entry in `questions.yaml`.
2. Give it a unique `id` (slug) and the German `question_de`.
3. Fill `expect.kind`:
   - `tool_call` — set `tool` to a name or a list of acceptable names
     (any one is a pass), and the `columns` / `operators` that must
     appear in the filter (any order). Leave them `[]` when the filter
     should be empty. Optional: `group_by` (column, or `null` to forbid
     grouping), `sort` (column, optional direction), `forbid_columns`,
     `max_conditions`. Add `min_rows` / `max_rows` only after you have
     counted on this snapshot.
   - `refusal` — set `reason` for humans; scoring checks that the model
     refused instead of calling a tool, not that the German wording matches.
     Set `outcome: [refused, answered]` so a prose refusal is accepted
     (`ask()` stores those as `answered`) but `error` / `no_answer` are not.
4. Re-run one case while editing the prompt:

   ```bash
   python tests/eval/run_eval.py --provider openai_compatible --id your-new-id
   ```

Criteria scored per question:

| criterion | pass when |
| --- | --- |
| tool match | at least one of the listed tool names appears in the recorded calls |
| column match | every listed column appears in the filter (aliases ok) |
| operator match | every listed operator appears |
| row-count plausible | `total_count` within `min_rows`/`max_rows` when those are set |
| group_by match | `group_by` equals the expected column, or is absent when the field is `null` |
| sort match | a tool call sorts on the expected column; direction only when specified |
| no forbidden columns | none of `forbid_columns` appear in any filter condition |
| condition count | no tool call has more filter conditions than `max_conditions` |
| outcome acceptable | `ask()` outcome is in `expect.outcome` (default `['answered']`; always scored) |
| refusal correct | `kind=refusal` and the model answered without a tool call |
| verification passed | outcome is not `answered_unverified` |

Omitted expect fields are `n/a` and do not count against the total, except
**outcome**, which is scored on every question. `error` and `no_answer` are
not in the default list, so a loop that burned the turn budget cannot fully
pass even if the tool/column/operator were right.

## `--mock`

`--mock` does not call a model. A scripted client emits the expected tool
call (or a stock refusal) so you can inspect the table format and the
scoring path. Tools still run against the real snapshot, so you need a
database and a complete snapshot. Use it when no local server is up — not
as a quality signal.
