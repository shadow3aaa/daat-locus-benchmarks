from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path

from daat_locus_benchmarks.models import BenchmarkTask
from daat_locus_benchmarks.workspace import collect_patch, prepare_workspace


class WorkspaceTests(unittest.TestCase):
    def test_prepare_workspace_checks_out_base_commit_and_collects_patch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source"
            source.mkdir()
            _git(["init", "-b", "main"], cwd=source)
            _git(["config", "user.name", "Test"], cwd=source)
            _git(["config", "user.email", "test@example.com"], cwd=source)
            (source / "hello.txt").write_text("hello\n", encoding="utf-8")
            _git(["add", "hello.txt"], cwd=source)
            _git(["commit", "-m", "initial"], cwd=source)
            base_commit = _git(["rev-parse", "HEAD"], cwd=source).stdout.strip()

            task = BenchmarkTask(
                id="local/repo",
                repo=str(source),
                base_commit=base_commit,
                problem_statement="change hello",
            )
            workspace = prepare_workspace(task, root / "workspaces")

            self.assertEqual(_git(["rev-parse", "HEAD"], cwd=workspace).stdout.strip(), base_commit)
            (workspace / "hello.txt").write_text("hello world\n", encoding="utf-8")
            (workspace / "new.txt").write_text("new\n", encoding="utf-8")
            patch = collect_patch(workspace)

        self.assertIn("diff --git a/hello.txt b/hello.txt", patch)
        self.assertIn("diff --git a/new.txt b/new.txt", patch)


def _git(args: list[str], *, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], cwd=cwd, text=True, capture_output=True, check=True)


if __name__ == "__main__":
    unittest.main()
