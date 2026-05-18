from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Mapping


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _required_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value)


@dataclass(frozen=True)
class BenchmarkTask:
    """A single coding benchmark task.

    The field names intentionally match common SWE-bench dataset columns while
    keeping the runner independent from any one dataset provider.
    """

    id: str
    problem_statement: str
    repo: str | None = None
    base_commit: str | None = None
    expected_patch: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any], default_id: str) -> "BenchmarkTask":
        canonical_keys = {
            "id",
            "instance_id",
            "repo",
            "base_commit",
            "problem_statement",
            "prompt",
            "issue",
            "patch",
            "test_patch",
        }
        task_id = _optional_str(data.get("id")) or _optional_str(data.get("instance_id")) or default_id
        problem_statement = (
            _required_text(data.get("problem_statement"))
            or _required_text(data.get("prompt"))
            or _required_text(data.get("issue"))
        )
        expected_patch = _optional_str(data.get("patch")) or _optional_str(data.get("test_patch"))
        metadata = {key: value for key, value in data.items() if key not in canonical_keys}
        return cls(
            id=task_id,
            repo=_optional_str(data.get("repo")),
            base_commit=_optional_str(data.get("base_commit")),
            problem_statement=problem_statement,
            expected_patch=expected_patch,
            metadata=metadata,
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class TaskRunResult:
    task_id: str
    status: str
    run_dir: str
    command: list[str]
    started_at: str
    finished_at: str
    duration_seconds: float
    return_code: int | None = None
    stdout_path: str | None = None
    stderr_path: str | None = None
    workspace_dir: str | None = None
    patch_path: str | None = None
    patch_bytes: int | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class RunSummary:
    run_id: str
    suite: str
    output_dir: str
    started_at: str
    finished_at: str
    results: list[TaskRunResult]
    predictions_path: str | None = None

    @property
    def total(self) -> int:
        return len(self.results)

    @property
    def passed(self) -> int:
        return self.count("passed")

    @property
    def failed(self) -> int:
        return self.count("failed")

    @property
    def planned(self) -> int:
        return self.count("planned")

    @property
    def timed_out(self) -> int:
        return self.count("timeout")

    @property
    def errored(self) -> int:
        return self.count("error")

    def count(self, status: str) -> int:
        return sum(1 for result in self.results if result.status == status)

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "suite": self.suite,
            "output_dir": self.output_dir,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "predictions_path": self.predictions_path,
            "total": self.total,
            "passed": self.passed,
            "failed": self.failed,
            "planned": self.planned,
            "timeout": self.timed_out,
            "error": self.errored,
            "results": [result.to_dict() for result in self.results],
        }
