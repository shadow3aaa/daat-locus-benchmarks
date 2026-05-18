from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Sequence

from .harness import build_harness_command, run_harness
from .runner import BenchmarkRunner
from .tasks import SUITES, TaskLoadError, list_suites, load_tasks


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="daat-locus-benchmarks",
        description="Pure Python/uv benchmark runner for Daat Locus coding-agent evaluations.",
    )
    subparsers = parser.add_subparsers(dest="command")

    subparsers.add_parser("list-suites", help="List supported benchmark suites.")

    run_parser = subparsers.add_parser("run", help="Run a benchmark suite or task file.")
    run_parser.add_argument("--suite", choices=sorted(SUITES), default="local-smoke", help="Benchmark suite name.")
    run_parser.add_argument("--tasks", type=Path, help="JSON or JSONL task file/directory. Required for SWE-bench suites.")
    run_parser.add_argument("--limit", type=int, help="Maximum number of tasks to run.")
    run_parser.add_argument("--output-dir", type=Path, default=Path("runs"), help="Directory for run artifacts.")
    run_parser.add_argument("--timeout", type=float, default=3600.0, help="Per-task timeout in seconds.")
    run_parser.add_argument("--dry-run", action="store_true", help="Materialize tasks and reports without executing an agent.")
    run_parser.add_argument(
        "--prepare-workspaces",
        action="store_true",
        help="Clone each task repo at base_commit, run the agent inside it, and collect git diff patches.",
    )
    run_parser.add_argument("--workspace-root", type=Path, help="Directory for mutable agent repo checkouts.")
    run_parser.add_argument("--repo-cache", type=Path, help="Optional local mirror/cache root keyed by repo name.")
    run_parser.add_argument("--predictions-path", type=Path, help="Write official SWE-bench predictions JSONL here.")
    run_parser.add_argument("--model-name", default="daat-locus", help="model_name_or_path value for predictions JSONL.")
    run_parser.add_argument(
        "--agent-command",
        help=(
            "Command executed once per task with DAAT_BENCHMARK_* environment variables. "
            "The command is split with shlex and executed with shell=False."
        ),
    )

    eval_parser = subparsers.add_parser("evaluate", help="Call the official SWE-bench harness on predictions JSONL.")
    eval_parser.add_argument("--predictions-path", type=Path, required=True, help="Official predictions JSONL path.")
    eval_parser.add_argument("--dataset-name", default="princeton-nlp/SWE-bench_Lite", help="SWE-bench dataset name.")
    eval_parser.add_argument("--split", default="test", help="Dataset split for harness evaluation.")
    eval_parser.add_argument("--max-workers", type=int, default=1, help="Official harness worker count.")
    eval_parser.add_argument("--run-id", default="daat-lite-smoke", help="Official harness run id.")
    eval_parser.add_argument("--print-only", action="store_true", help="Print the harness command without executing it.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command is None:
        parser.print_help()
        return 0
    if args.command == "list-suites":
        _print_suites()
        return 0
    if args.command == "run":
        return _run(args)
    if args.command == "evaluate":
        return _evaluate(args)

    parser.error(f"unknown command: {args.command}")
    return 2


def _print_suites() -> None:
    for suite in list_suites():
        marker = "requires --tasks" if suite.requires_tasks_file else "built-in"
        print(f"{suite.name:20} {marker:16} {suite.description}")


def _run(args: argparse.Namespace) -> int:
    if not args.dry_run and not args.agent_command:
        print("error: --agent-command is required unless --dry-run is set", file=sys.stderr)
        return 2

    try:
        tasks = load_tasks(args.suite, tasks_path=args.tasks, limit=args.limit)
    except TaskLoadError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    runner = BenchmarkRunner(
        suite=args.suite,
        output_dir=args.output_dir,
        agent_command=args.agent_command,
        dry_run=args.dry_run,
        timeout_seconds=args.timeout,
        prepare_workspaces=args.prepare_workspaces,
        workspace_root=args.workspace_root,
        repo_cache=args.repo_cache,
        predictions_path=args.predictions_path,
        model_name=args.model_name,
    )
    summary = runner.run(tasks)
    _print_summary(summary)
    return 0 if summary.failed == 0 and summary.timed_out == 0 and summary.errored == 0 else 1


def _evaluate(args: argparse.Namespace) -> int:
    command = build_harness_command(
        predictions_path=args.predictions_path,
        dataset_name=args.dataset_name,
        split=args.split,
        run_id=args.run_id,
        max_workers=args.max_workers,
    )
    print(" ".join(command))
    if args.print_only:
        return 0
    return run_harness(command).returncode


def _print_summary(summary: object) -> None:
    print(f"run_id={summary.run_id}")
    print(f"suite={summary.suite}")
    print(f"output_dir={summary.output_dir}")
    if summary.predictions_path:
        print(f"predictions_path={summary.predictions_path}")
    print(
        "totals="
        f"total:{summary.total} "
        f"passed:{summary.passed} "
        f"planned:{summary.planned} "
        f"failed:{summary.failed} "
        f"timeout:{summary.timed_out} "
        f"error:{summary.errored}"
    )
    for result in summary.results:
        print(f"- {result.task_id}: {result.status} ({result.duration_seconds:.3f}s) {result.run_dir}")
