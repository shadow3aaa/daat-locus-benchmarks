# daat-locus-benchmarks

Independent benchmark runner for Daat Locus.

This repository hosts Python/uv tooling for running coding-agent benchmarks. It
starts with a local smoke path and supports SWE-bench Lite / SWE-bench Verified
style task files without introducing shell-script runner glue.

## Current scope

- Pure Python CLI, installed as `daat-locus-benchmarks`.
- Built-in `local-smoke` suite for validating runner plumbing.
- `swebench-lite` and `swebench-verified` suite names that can fetch task rows
  from Hugging Face or accept local JSON/JSONL exports.
- Optional SWE-bench workspace mode that clones each task repo at
  `base_commit`, runs the agent inside that checkout, collects `git diff
  --binary`, and writes official `predictions.jsonl` rows.
- Optional `evaluate` command that shells out to the official SWE-bench harness
  module with `shell=False`.
- Per-task run directories containing `task.json`, `prompt.md`, `stdout.txt`,
  `stderr.txt`, optional `model.patch`, plus run-level `summary.json`,
  `results.jsonl`, and optional `predictions.jsonl`.
- Built-in Daat Locus adapter using `daat-locus send --raw`; the benchmark
  prompt is sent on stdin and the CLI waits for the daemon reply.
- Agent commands are executed with `subprocess.run(..., shell=False)` and receive
  `DAAT_BENCHMARK_*` environment variables.

## Development

```bash
uv venv
uv run daat-locus-benchmarks list-suites
uv run daat-locus-benchmarks run --suite local-smoke --dry-run
uv run python -m unittest discover -s tests
```

## Run the local smoke benchmark

```bash
uv run daat-locus-benchmarks run \
  --suite local-smoke \
  --agent-command "python3 -c 'import os; print(os.environ[\"DAAT_BENCHMARK_TASK_ID\"])'"
```

## Run a SWE-bench style task file

Prepare a `.jsonl` file with fields such as `instance_id`, `repo`,
`base_commit`, and `problem_statement`. Gold `patch` and `test_patch` columns
are ignored by task loading/export and are never included in prompts.

You can also export the first rows directly from Hugging Face:

```bash
uv run daat-locus-benchmarks export-tasks \
  --suite swebench-lite \
  --limit 5 \
  --output data/swebench_lite.jsonl
```

```bash
uv run daat-locus-benchmarks run \
  --suite swebench-lite \
  --tasks data/swebench_lite.jsonl \
  --limit 5 \
  --use-daat-locus-send
```

Each agent process receives:

- `DAAT_BENCHMARK_SUITE`
- `DAAT_BENCHMARK_TASK_ID`
- `DAAT_BENCHMARK_REPO`
- `DAAT_BENCHMARK_BASE_COMMIT`
- `DAAT_BENCHMARK_PROMPT`
- `DAAT_BENCHMARK_TASK_JSON`
- `DAAT_BENCHMARK_OUTPUT_DIR`
- `DAAT_BENCHMARK_WORKSPACE`
- `DAAT_BENCHMARK_PATCH_PATH`
- `DAAT_BENCHMARK_PROBLEM_STATEMENT`

## SWE-bench Lite workflow

The runner does not replace the official SWE-bench harness. It prepares a
mutable checkout for Daat Locus, collects the patch, then hands only
`instance_id + model_patch` to the official harness.

```text
SWE-bench instance
  -> clone repo into an agent workspace
  -> checkout instance.base_commit
  -> render prompt.md
  -> run Daat Locus inside DAAT_BENCHMARK_WORKSPACE
  -> collect git diff --binary as model.patch
  -> write official predictions.jsonl
  -> call official swebench.harness.run_evaluation
```

For a small Lite smoke, either run directly from the Hugging Face rows API or
first export a JSONL file. A dry-run check that fetches one Lite row and renders
prompt/report artifacts without running an agent looks like this:

```bash
uv run daat-locus-benchmarks run \
  --suite swebench-lite \
  --limit 1 \
  --output-dir runs/lite-dry-run \
  --dry-run
```

To run Daat Locus on a few real Lite instances and produce harness predictions:

```bash
uv run daat-locus-benchmarks run \
  --suite swebench-lite \
  --limit 3 \
  --prepare-workspaces \
  --workspace-root workspaces/lite-smoke \
  --predictions-path predictions/lite-smoke.jsonl \
  --use-daat-locus-send
```

With `--use-daat-locus-send`, the runner executes `daat-locus send --raw` with
`cwd=$DAAT_BENCHMARK_WORKSPACE` and sends the rendered benchmark prompt on
stdin. `daat-locus send` connects to the Daat Locus daemon, waits for the final
reply, and exits. After it exits successfully, the runner records `model.patch`
from that checkout and writes rows like:

```jsonl
{"instance_id":"django__django-xxxxx","model_name_or_path":"daat-locus","model_patch":"diff --git ..."}
```

Use `--agent-command` only when testing a custom adapter command. It is mutually
exclusive with `--use-daat-locus-send`.

Then run the official harness. The command below requires the official
SWE-bench package and Docker environment to be installed separately:

```bash
uv run daat-locus-benchmarks evaluate \
  --predictions-path predictions/lite-smoke.jsonl \
  --dataset-name princeton-nlp/SWE-bench_Lite \
  --split test \
  --max-workers 1 \
  --run-id daat-lite-smoke
```

Use `--print-only` to inspect the exact official harness command without
running Docker:

```bash
uv run daat-locus-benchmarks evaluate \
  --predictions-path predictions/lite-smoke.jsonl \
  --print-only
```
