from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
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
    remote_dataset: str | None = None
    remote_config: str = "default"
    remote_split: str = "test"


SUITES: dict[str, SuiteInfo] = {
    "local-smoke": SuiteInfo(
        name="local-smoke",
        description="Built-in single task for checking runner plumbing without network or dataset access.",
    ),
    "swebench-lite": SuiteInfo(
        name="swebench-lite",
        description="SWE-bench Lite tasks fetched from Hugging Face or loaded from a JSON/JSONL file.",
        remote_dataset="princeton-nlp/SWE-bench_Lite",
    ),
    "swebench-verified": SuiteInfo(
        name="swebench-verified",
        description="SWE-bench Verified tasks fetched from Hugging Face or loaded from a JSON/JSONL file.",
        remote_dataset="princeton-nlp/SWE-bench_Verified",
    ),
}


DATASETS_SERVER_ROWS_URL = "https://datasets-server.huggingface.co/rows"
DATASET_PAGE_SIZE = 100


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
        elif SUITES[suite].remote_dataset:
            tasks = list(_fetch_remote_suite_tasks(SUITES[suite], limit=limit))
        else:
            raise TaskLoadError(f"suite {suite!r} requires --tasks with a JSON or JSONL task file")
    else:
        tasks = list(_load_task_path(tasks_path))

    if limit is not None:
        tasks = tasks[:limit]

    if not tasks:
        raise TaskLoadError("no benchmark tasks loaded")
    return tasks


def export_tasks(
    suite: str,
    output_path: Path,
    *,
    tasks_path: Path | None = None,
    limit: int | None = None,
) -> list[BenchmarkTask]:
    tasks = load_tasks(suite, tasks_path=tasks_path, limit=limit)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as file:
        for task in tasks:
            file.write(json.dumps(task.to_dict(), sort_keys=True, ensure_ascii=False) + "\n")
    return tasks


def _fetch_remote_suite_tasks(suite: SuiteInfo, *, limit: int | None = None) -> Iterable[BenchmarkTask]:
    if not suite.remote_dataset:
        raise TaskLoadError(f"suite {suite.name!r} does not define a remote dataset")

    offset = 0
    remaining = limit
    while remaining is None or remaining > 0:
        page_length = DATASET_PAGE_SIZE if remaining is None else min(DATASET_PAGE_SIZE, remaining)
        payload = _fetch_dataset_rows(
            suite.remote_dataset,
            config=suite.remote_config,
            split=suite.remote_split,
            offset=offset,
            length=page_length,
        )
        rows = payload.get("rows")
        if not isinstance(rows, list) or not rows:
            break
        for index, row_payload in enumerate(rows, start=offset + 1):
            if not isinstance(row_payload, Mapping):
                raise TaskLoadError(f"unexpected row payload for {suite.name}[{index}]")
            row = row_payload.get("row", row_payload)
            if not isinstance(row, Mapping):
                raise TaskLoadError(f"unexpected row object for {suite.name}[{index}]")
            yield _task_from_remote_row(row, default_id=f"{suite.name}-{index}", suite=suite)

        offset += len(rows)
        if remaining is not None:
            remaining -= len(rows)
        total = payload.get("num_rows_total")
        if isinstance(total, int) and offset >= total:
            break


def _fetch_dataset_rows(
    dataset: str,
    *,
    config: str,
    split: str,
    offset: int,
    length: int,
) -> Mapping[str, Any]:
    query = urllib.parse.urlencode(
        {"dataset": dataset, "config": config, "split": split, "offset": offset, "length": length}
    )
    url = f"{DATASETS_SERVER_ROWS_URL}?{query}"
    try:
        with urllib.request.urlopen(url, timeout=60) as response:
            payload = json.load(response)
    except urllib.error.URLError as exc:
        raise TaskLoadError(f"failed to fetch {dataset} rows from Hugging Face: {exc}") from exc

    if not isinstance(payload, Mapping):
        raise TaskLoadError(f"unexpected response from Hugging Face rows API for {dataset}")
    return payload


def _task_from_remote_row(row: Mapping[str, Any], *, default_id: str, suite: SuiteInfo) -> BenchmarkTask:
    task = BenchmarkTask.from_mapping(row, default_id=default_id)
    metadata = {
        "suite": suite.name,
        "dataset": suite.remote_dataset,
        "dataset_config": suite.remote_config,
        "dataset_split": suite.remote_split,
    }
    metadata.update(task.metadata)
    return BenchmarkTask(
        id=task.id,
        repo=task.repo,
        base_commit=task.base_commit,
        problem_statement=task.problem_statement,
        expected_patch=task.expected_patch,
        metadata=metadata,
    )


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
