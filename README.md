# daat-locus-benchmarks

Independent benchmark runner for Daat Locus.

This repository hosts Python/uv tooling for running coding-agent benchmarks. It
starts with a local smoke path and supports SWE-bench Lite / SWE-bench Verified
style task files without introducing shell-script runner glue.

## Current scope

- Pure Python CLI, installed as `daat-locus-benchmarks`.
- Built-in `local-smoke` suite for validating runner plumbing.
- `swebench-lite` and `swebench-verified` suite names that accept local JSON or
  JSONL task exports.
- Optional SWE-bench workspace mode that clones each task repo at
  `base_commit`, runs the agent inside that checkout, collects `git diff
  --binary`, and writes official `predictions.jsonl` rows.
- Optional `evaluate` command that shells out to the official SWE-bench harness
  module with `shell=False`.
- Per-task run directories containing `task.json`, `prompt.md`, `stdout.txt`,
  `stderr.txt`, optional `model.patch`, plus run-level `summary.json`,
  `results.jsonl`, and optional `predictions.jsonl`.
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
`base_commit`, `problem_statement`, and optionally `patch` or `test_patch`.

```bash
uv run daat-locus-benchmarks run \
  --suite swebench-lite \
  --tasks data/swebench_lite.jsonl \
  --limit 5 \
  --agent-command "your-agent-command --non-interactive"
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

For a small Lite smoke, first export or create a JSONL file with real
SWE-bench Lite fields such as `instance_id`, `repo`, `base_commit`, and
`problem_statement`, then limit it to a few tasks:

```bash
uv run daat-locus-benchmarks run \
  --suite swebench-lite \
  --tasks data/swebench_lite.jsonl \
  --limit 3 \
  --prepare-workspaces \
  --workspace-root workspaces/lite-smoke \
  --predictions-path predictions/lite-smoke.jsonl \
  --agent-command "daat-locus --non-interactive"
```

The agent command is executed with `cwd=$DAAT_BENCHMARK_WORKSPACE`. After it
exits successfully, the runner records `model.patch` from that checkout and
writes rows like:

```jsonl
{"instance_id":"django__django-xxxxx","model_name_or_path":"daat-locus","model_patch":"diff --git ..."}
```

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
