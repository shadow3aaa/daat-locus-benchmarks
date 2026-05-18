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
- Per-task run directories containing `task.json`, `prompt.md`, `stdout.txt`,
  `stderr.txt`, plus run-level `summary.json` and `results.jsonl`.
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
- `DAAT_BENCHMARK_PROBLEM_STATEMENT`
