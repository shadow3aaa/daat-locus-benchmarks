from __future__ import annotations

import os
import re
import shlex
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Sequence

from .models import BenchmarkTask, RunSummary, TaskRunResult
from .predictions import Prediction, prediction_from_patch, write_predictions
from .reporting import write_json, write_jsonl
from .workspace import WorkspaceError, collect_patch, prepare_workspace


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
        prepare_workspaces: bool = False,
        workspace_root: Path | None = None,
        repo_cache: Path | None = None,
        predictions_path: Path | None = None,
        model_name: str = "daat-locus",
        use_daat_locus_send: bool = False,
        daat_locus_binary: str = "daat-locus",
    ) -> None:
        if agent_command is not None and use_daat_locus_send:
            raise ValueError("choose either agent_command or use_daat_locus_send, not both")
        self.suite = suite
        self.output_dir = output_dir
        self.agent_command = agent_command
        self.dry_run = dry_run
        self.timeout_seconds = timeout_seconds
        self.prepare_workspaces = prepare_workspaces
        self.workspace_root = workspace_root
        self.repo_cache = repo_cache
        self.predictions_path = predictions_path
        self.model_name = model_name
        self.use_daat_locus_send = use_daat_locus_send
        self.daat_locus_binary = daat_locus_binary

    def run(self, tasks: Iterable[BenchmarkTask]) -> RunSummary:
        task_list = list(tasks)
        started_at = _utc_now()
        run_id = _run_id(started_at)
        run_root = (self.output_dir / run_id).resolve()
        run_root.mkdir(parents=True, exist_ok=False)

        workspaces_root = (self.workspace_root or run_root / "workspaces").resolve()
        results: list[TaskRunResult] = []
        predictions: list[Prediction] = []
        for index, task in enumerate(task_list, start=1):
            result, prediction = self.run_task(task, index, run_root, workspaces_root)
            results.append(result)
            if prediction is not None:
                predictions.append(prediction)

        final_predictions_path: Path | None = None
        if self.predictions_path is not None:
            final_predictions_path = self.predictions_path.resolve()
        elif predictions:
            final_predictions_path = run_root / "predictions.jsonl"
        if final_predictions_path is not None:
            write_predictions(final_predictions_path, predictions)

        finished_at = _utc_now()
        summary = RunSummary(
            run_id=run_id,
            suite=self.suite,
            output_dir=str(run_root),
            started_at=_isoformat(started_at),
            finished_at=_isoformat(finished_at),
            results=results,
            predictions_path=str(final_predictions_path) if final_predictions_path is not None else None,
        )
        write_json(run_root / "summary.json", summary.to_dict())
        write_jsonl(run_root / "results.jsonl", (result.to_dict() for result in results))
        return summary

    def run_task(
        self,
        task: BenchmarkTask,
        index: int,
        run_root: Path,
        workspaces_root: Path,
    ) -> tuple[TaskRunResult, Prediction | None]:
        task_dir = run_root / f"{index:04d}-{_slug(task.id)}"
        task_dir.mkdir(parents=True, exist_ok=False)

        task_json = task_dir / "task.json"
        prompt_path = task_dir / "prompt.md"
        stdout_path = task_dir / "stdout.txt"
        stderr_path = task_dir / "stderr.txt"

        write_json(task_json, task.to_dict())

        command = self._agent_command()
        workspace_dir: Path | None = None
        patch_path = task_dir / "model.patch"
        started_at = _utc_now()

        if self.prepare_workspaces:
            try:
                workspace_dir = prepare_workspace(task, workspaces_root, repo_cache=self.repo_cache)
            except WorkspaceError as exc:
                stdout_path.write_text("", encoding="utf-8")
                stderr_path.write_text(f"{type(exc).__name__}: {exc}\n", encoding="utf-8")
                finished_at = _utc_now()
                return (
                    TaskRunResult(
                        task_id=task.id,
                        status="error",
                        run_dir=str(task_dir),
                        command=command,
                        started_at=_isoformat(started_at),
                        finished_at=_isoformat(finished_at),
                        duration_seconds=_elapsed(started_at, finished_at),
                        stdout_path=str(stdout_path),
                        stderr_path=str(stderr_path),
                        workspace_dir=str(workspace_dir) if workspace_dir is not None else None,
                        error=str(exc),
                    ),
                    None,
                )

        prompt_text = _render_prompt(
            task,
            workspace_dir=workspace_dir or task_dir,
            task_dir=task_dir,
            patch_path=patch_path,
        )
        prompt_path.write_text(prompt_text, encoding="utf-8")

        if self.dry_run:
            stdout_path.write_text("", encoding="utf-8")
            stderr_path.write_text("", encoding="utf-8")
            finished_at = _utc_now()
            return (
                TaskRunResult(
                    task_id=task.id,
                    status="planned",
                    run_dir=str(task_dir),
                    command=command,
                    started_at=_isoformat(started_at),
                    finished_at=_isoformat(finished_at),
                    duration_seconds=_elapsed(started_at, finished_at),
                    stdout_path=str(stdout_path),
                    stderr_path=str(stderr_path),
                    workspace_dir=str(workspace_dir) if workspace_dir is not None else None,
                ),
                None,
            )

        if not command:
            raise ValueError("agent_command or use_daat_locus_send is required unless dry_run is true")

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
                "DAAT_BENCHMARK_WORKSPACE": str(workspace_dir or task_dir),
                "DAAT_BENCHMARK_PATCH_PATH": str(patch_path),
                "DAAT_BENCHMARK_PROBLEM_STATEMENT": task.problem_statement,
            }
        )

        return_code: int | None
        error: str | None = None
        try:
            completed = subprocess.run(
                command,
                cwd=workspace_dir or task_dir,
                env=env,
                input=prompt_text if self.use_daat_locus_send else None,
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
        prediction: Prediction | None = None
        patch_bytes: int | None = None
        if workspace_dir is not None and status == "passed":
            try:
                patch = collect_patch(workspace_dir)
                patch_path.write_text(patch, encoding="utf-8")
                patch_bytes = len(patch.encode("utf-8"))
                prediction = prediction_from_patch(task, patch, model_name=self.model_name)
            except WorkspaceError as exc:
                status = "error"
                error = str(exc)
                stderr_path.write_text(stderr + f"\n{type(exc).__name__}: {exc}\n", encoding="utf-8")
        finished_at = _utc_now()
        return (
            TaskRunResult(
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
                workspace_dir=str(workspace_dir) if workspace_dir is not None else None,
                patch_path=str(patch_path) if patch_bytes is not None else None,
                patch_bytes=patch_bytes,
                error=error,
            ),
            prediction,
        )

    def _agent_command(self) -> list[str]:
        if self.use_daat_locus_send:
            return [self.daat_locus_binary, "send", "--raw"]
        if self.agent_command is None:
            return []
        return _normalize_command(self.agent_command)


def _render_prompt(
    task: BenchmarkTask,
    *,
    workspace_dir: Path,
    task_dir: Path,
    patch_path: Path,
) -> str:
    parts = [
        f"# Benchmark task: {task.id}",
        "",
        f"Repository: {task.repo or 'unspecified'}",
        f"Base commit: {task.base_commit or 'unspecified'}",
        "",
        "## Runner context",
        "",
        f"Agent workspace: {workspace_dir}",
        f"Run artifact directory: {task_dir}",
        f"Patch artifact path: {patch_path}",
        "",
        "Modify files inside the agent workspace only. Do not commit changes; the benchmark runner will collect git diff --binary after you finish.",
        "",
        "## Problem statement",
        "",
        task.problem_statement.rstrip() or "(empty)",
        "",
    ]
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
