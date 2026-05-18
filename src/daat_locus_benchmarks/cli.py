from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Sequence

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
        "--agent-command",
        help=(
            "Command executed once per task with DAAT_BENCHMARK_* environment variables. "
            "The command is split with shlex and executed with shell=False."
        ),
    )
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
    )
    summary = runner.run(tasks)
    _print_summary(summary)
    return 0 if summary.failed == 0 and summary.timed_out == 0 and summary.errored == 0 else 1


def _print_summary(summary: object) -> None:
    print(f"run_id={summary.run_id}")
    print(f"suite={summary.suite}")
    print(f"output_dir={summary.output_dir}")
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
