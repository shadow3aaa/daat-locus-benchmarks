from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping

from .models import BenchmarkTask


class TaskLoadError(ValueError):
    """Raised when benchmark tasks cannot be loaded."""


@dataclass(frozen=True)
class SuiteInfo:
    name: str
    description: str
    requires_tasks_file: bool = False


SUITES: dict[str, SuiteInfo] = {
    "local-smoke": SuiteInfo(
        name="local-smoke",
        description="Built-in single task for checking runner plumbing without network or dataset access.",
    ),
    "swebench-lite": SuiteInfo(
        name="swebench-lite",
        description="SWE-bench Lite compatible tasks loaded from a JSON or JSONL file.",
        requires_tasks_file=True,
    ),
    "swebench-verified": SuiteInfo(
        name="swebench-verified",
        description="SWE-bench Verified compatible tasks loaded from a JSON or JSONL file.",
        requires_tasks_file=True,
    ),
}


LOCAL_SMOKE_TASKS = [
    BenchmarkTask(
        id="local-smoke/echo-env",
        repo="local",
        base_commit="workspace",
        problem_statement=(
            "Smoke task: read the prompt path from DAAT_BENCHMARK_PROMPT, "
            "then print a short acknowledgement. This validates CLI, task "
            "materialization, subprocess execution, and report writing."
        ),
        metadata={"suite": "local-smoke"},
    )
]


def list_suites() -> Iterable[SuiteInfo]:
    return SUITES.values()


def load_tasks(suite: str, tasks_path: Path | None = None, limit: int | None = None) -> list[BenchmarkTask]:
    if suite not in SUITES:
        names = ", ".join(sorted(SUITES))
        raise TaskLoadError(f"unknown suite {suite!r}; expected one of: {names}")

    if limit is not None and limit < 1:
        raise TaskLoadError("--limit must be greater than zero")

    if tasks_path is None:
        if suite == "local-smoke":
            tasks = list(LOCAL_SMOKE_TASKS)
        else:
            raise TaskLoadError(f"suite {suite!r} requires --tasks with a JSON or JSONL task file")
    else:
        tasks = list(_load_task_path(tasks_path))

    if limit is not None:
        tasks = tasks[:limit]

    if not tasks:
        raise TaskLoadError("no benchmark tasks loaded")
    return tasks


def _load_task_path(path: Path) -> Iterable[BenchmarkTask]:
    if not path.exists():
        raise TaskLoadError(f"task path does not exist: {path}")
    if path.is_dir():
        files = sorted([*path.glob("*.json"), *path.glob("*.jsonl")])
        if not files:
            raise TaskLoadError(f"directory has no .json or .jsonl task files: {path}")
        for file_path in files:
            yield from _load_task_file(file_path)
        return
    yield from _load_task_file(path)


def _load_task_file(path: Path) -> Iterable[BenchmarkTask]:
    suffix = path.suffix.lower()
    if suffix == ".jsonl":
        yield from _load_jsonl(path)
    elif suffix == ".json":
        yield from _load_json(path)
    else:
        raise TaskLoadError(f"unsupported task file extension for {path}; use .json or .jsonl")


def _load_json(path: Path) -> Iterable[BenchmarkTask]:
    with path.open(encoding="utf-8") as file:
        payload = json.load(file)

    if isinstance(payload, list):
        yield from _tasks_from_mappings(payload, path.stem)
        return
    if isinstance(payload, Mapping):
        for key in ("tasks", "instances", "rows"):
            rows = payload.get(key)
            if isinstance(rows, list):
                yield from _tasks_from_mappings(rows, path.stem)
                return
        yield BenchmarkTask.from_mapping(payload, default_id=path.stem)
        return

    raise TaskLoadError(f"expected JSON object or array in {path}")


def _load_jsonl(path: Path) -> Iterable[BenchmarkTask]:
    with path.open(encoding="utf-8") as file:
        for index, line in enumerate(file, start=1):
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            payload = json.loads(stripped)
            if not isinstance(payload, Mapping):
                raise TaskLoadError(f"expected object at {path}:{index}")
            yield BenchmarkTask.from_mapping(payload, default_id=f"{path.stem}-{index}")


def _tasks_from_mappings(rows: Iterable[Any], stem: str) -> Iterable[BenchmarkTask]:
    for index, row in enumerate(rows, start=1):
        if not isinstance(row, Mapping):
            raise TaskLoadError(f"expected task object at {stem}[{index}]")
        yield BenchmarkTask.from_mapping(row, default_id=f"{stem}-{index}")
