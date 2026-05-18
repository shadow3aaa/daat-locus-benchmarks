from __future__ import annotations

import os
import re
import shlex
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Sequence

from .models import BenchmarkTask, RunSummary, TaskRunResult
from .reporting import write_json, write_jsonl


Command = str | Sequence[str]


class BenchmarkRunner:
    """Materialize benchmark tasks and execute an agent command for each one."""

    def __init__(
        self,
        *,
        suite: str,
        output_dir: Path,
        agent_command: Command | None = None,
        dry_run: bool = False,
        timeout_seconds: float = 3600.0,
    ) -> None:
        self.suite = suite
        self.output_dir = output_dir
        self.agent_command = agent_command
        self.dry_run = dry_run
        self.timeout_seconds = timeout_seconds

    def run(self, tasks: Iterable[BenchmarkTask]) -> RunSummary:
        task_list = list(tasks)
        started_at = _utc_now()
        run_id = _run_id(started_at)
        run_root = self.output_dir / run_id
        run_root.mkdir(parents=True, exist_ok=False)

        results = [self.run_task(task, index, run_root) for index, task in enumerate(task_list, start=1)]
        finished_at = _utc_now()
        summary = RunSummary(
            run_id=run_id,
            suite=self.suite,
            output_dir=str(run_root),
            started_at=_isoformat(started_at),
            finished_at=_isoformat(finished_at),
            results=results,
        )
        write_json(run_root / "summary.json", summary.to_dict())
        write_jsonl(run_root / "results.jsonl", (result.to_dict() for result in results))
        return summary

    def run_task(self, task: BenchmarkTask, index: int, run_root: Path) -> TaskRunResult:
        task_dir = run_root / f"{index:04d}-{_slug(task.id)}"
        task_dir.mkdir(parents=True, exist_ok=False)

        task_json = task_dir / "task.json"
        prompt_path = task_dir / "prompt.md"
        stdout_path = task_dir / "stdout.txt"
        stderr_path = task_dir / "stderr.txt"

        write_json(task_json, task.to_dict())
        prompt_path.write_text(_render_prompt(task), encoding="utf-8")

        command = [] if self.agent_command is None else _normalize_command(self.agent_command)
        started_at = _utc_now()

        if self.dry_run:
            stdout_path.write_text("", encoding="utf-8")
            stderr_path.write_text("", encoding="utf-8")
            finished_at = _utc_now()
            return TaskRunResult(
                task_id=task.id,
                status="planned",
                run_dir=str(task_dir),
                command=command,
                started_at=_isoformat(started_at),
                finished_at=_isoformat(finished_at),
                duration_seconds=_elapsed(started_at, finished_at),
                stdout_path=str(stdout_path),
                stderr_path=str(stderr_path),
            )

        if not command:
            raise ValueError("agent_command is required unless dry_run is true")

        env = os.environ.copy()
        env.update(
            {
                "DAAT_BENCHMARK_SUITE": self.suite,
                "DAAT_BENCHMARK_TASK_ID": task.id,
                "DAAT_BENCHMARK_REPO": task.repo or "",
                "DAAT_BENCHMARK_BASE_COMMIT": task.base_commit or "",
                "DAAT_BENCHMARK_PROMPT": str(prompt_path),
                "DAAT_BENCHMARK_TASK_JSON": str(task_json),
                "DAAT_BENCHMARK_OUTPUT_DIR": str(task_dir),
                "DAAT_BENCHMARK_PROBLEM_STATEMENT": task.problem_statement,
            }
        )

        return_code: int | None
        error: str | None = None
        try:
            completed = subprocess.run(
                command,
                cwd=task_dir,
                env=env,
                text=True,
                capture_output=True,
                timeout=self.timeout_seconds,
                check=False,
            )
            stdout = completed.stdout
            stderr = completed.stderr
            return_code = completed.returncode
            status = "passed" if completed.returncode == 0 else "failed"
        except subprocess.TimeoutExpired as exc:
            stdout = _to_text(exc.stdout)
            stderr = _to_text(exc.stderr) + f"\nTimed out after {self.timeout_seconds} seconds.\n"
            return_code = None
            status = "timeout"
            error = f"timed out after {self.timeout_seconds} seconds"
        except OSError as exc:
            stdout = ""
            stderr = f"{type(exc).__name__}: {exc}\n"
            return_code = None
            status = "error"
            error = str(exc)

        stdout_path.write_text(stdout, encoding="utf-8")
        stderr_path.write_text(stderr, encoding="utf-8")
        finished_at = _utc_now()
        return TaskRunResult(
            task_id=task.id,
            status=status,
            run_dir=str(task_dir),
            command=command,
            started_at=_isoformat(started_at),
            finished_at=_isoformat(finished_at),
            duration_seconds=_elapsed(started_at, finished_at),
            return_code=return_code,
            stdout_path=str(stdout_path),
            stderr_path=str(stderr_path),
            error=error,
        )


def _render_prompt(task: BenchmarkTask) -> str:
    parts = [
        f"# Benchmark task: {task.id}",
        "",
        f"Repository: {task.repo or 'unspecified'}",
        f"Base commit: {task.base_commit or 'unspecified'}",
        "",
        "## Problem statement",
        "",
        task.problem_statement.rstrip() or "(empty)",
        "",
    ]
    if task.expected_patch:
        parts.extend(["## Reference patch", "", task.expected_patch.rstrip(), ""])
    return "\n".join(parts)


def _normalize_command(command: Command) -> list[str]:
    if isinstance(command, str):
        result = shlex.split(command)
    else:
        result = [str(part) for part in command]
    if not result:
        raise ValueError("agent command cannot be empty")
    return result


def _slug(value: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9_.-]+", "-", value).strip("-._")
    return (slug or "task")[:80]


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _run_id(started_at: datetime) -> str:
    return started_at.strftime("%Y%m%dT%H%M%SZ")


def _isoformat(value: datetime) -> str:
    return value.isoformat(timespec="seconds").replace("+00:00", "Z")


def _elapsed(started_at: datetime, finished_at: datetime) -> float:
    return round((finished_at - started_at).total_seconds(), 3)


def _to_text(value: str | bytes | None) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value
