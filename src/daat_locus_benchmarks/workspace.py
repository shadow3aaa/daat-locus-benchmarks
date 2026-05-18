from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

from .models import BenchmarkTask


class WorkspaceError(RuntimeError):
    """Raised when an agent workspace cannot be prepared or inspected."""


def prepare_workspace(task: BenchmarkTask, workspace_root: Path, *, repo_cache: Path | None = None) -> Path:
    """Clone and checkout a benchmark instance workspace for an agent.

    The returned directory is the mutable repo checkout that the agent should
    edit. It is intentionally separate from official SWE-bench harness state:
    only the resulting git diff is passed to the harness later.
    """

    if not task.repo:
        raise WorkspaceError(f"task {task.id!r} does not define a repo")
    if not task.base_commit:
        raise WorkspaceError(f"task {task.id!r} does not define a base_commit")

    workspace_root.mkdir(parents=True, exist_ok=True)
    repo_dir = workspace_root / _slug(task.id)
    if repo_dir.exists():
        shutil.rmtree(repo_dir)

    source = _repo_source(task.repo, repo_cache=repo_cache)
    _run_git(["clone", "--no-tags", source, str(repo_dir)], cwd=workspace_root)
    _run_git(["checkout", "--detach", task.base_commit], cwd=repo_dir)
    _run_git(["reset", "--hard", task.base_commit], cwd=repo_dir)
    _run_git(["clean", "-fdx"], cwd=repo_dir)
    return repo_dir


def collect_patch(workspace_dir: Path) -> str:
    """Return a binary-safe git diff for tracked and newly-created files."""

    untracked = _run_git(["ls-files", "--others", "--exclude-standard"], cwd=workspace_dir).stdout.splitlines()
    if untracked:
        _run_git(["add", "-N", "--", *untracked], cwd=workspace_dir)
    return _run_git(["diff", "--binary"], cwd=workspace_dir).stdout


def _repo_source(repo: str, *, repo_cache: Path | None) -> str:
    if repo.startswith(("http://", "https://", "git@", "ssh://", "file://", "/", "./", "../")):
        return repo
    if repo_cache is not None:
        cached = repo_cache / repo
        if cached.exists():
            return str(cached)
    return f"https://github.com/{repo}.git"


def _run_git(args: list[str], *, cwd: Path) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            ["git", *args],
            cwd=cwd,
            text=True,
            capture_output=True,
            check=True,
        )
    except subprocess.CalledProcessError as exc:
        message = exc.stderr.strip() or exc.stdout.strip() or str(exc)
        raise WorkspaceError(f"git {' '.join(args)} failed in {cwd}: {message}") from exc


def _slug(value: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9_.-]+", "-", value).strip("-._")
    return (slug or "task")[:100]
