from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from daat_locus_benchmarks.models import BenchmarkTask
from daat_locus_benchmarks.runner import BenchmarkRunner


class BenchmarkRunnerTests(unittest.TestCase):
    def test_dry_run_writes_summary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            runner = BenchmarkRunner(suite="local-smoke", output_dir=Path(tmp), dry_run=True)
            summary = runner.run([BenchmarkTask(id="task-1", problem_statement="hello")])

            self.assertEqual(summary.total, 1)
            self.assertEqual(summary.planned, 1)
            self.assertTrue((Path(summary.output_dir) / "summary.json").exists())
            self.assertTrue((Path(summary.results[0].run_dir) / "prompt.md").exists())

    def test_agent_command_receives_environment(self) -> None:
        command = [
            sys.executable,
            "-c",
            "import os, pathlib; pathlib.Path('agent.txt').write_text(os.environ['DAAT_BENCHMARK_TASK_ID']); print('ok')",
        ]
        with tempfile.TemporaryDirectory() as tmp:
            runner = BenchmarkRunner(suite="local-smoke", output_dir=Path(tmp), agent_command=command)
            summary = runner.run([BenchmarkTask(id="task-env", problem_statement="hello")])

            self.assertEqual(summary.passed, 1)
            task_dir = Path(summary.results[0].run_dir)
            self.assertEqual((task_dir / "agent.txt").read_text(encoding="utf-8"), "task-env")
            self.assertEqual((task_dir / "stdout.txt").read_text(encoding="utf-8").strip(), "ok")

    def test_workspace_run_collects_prediction_patch(self) -> None:
        command = [
            sys.executable,
            "-c",
            "import os, pathlib; pathlib.Path(os.environ['DAAT_BENCHMARK_WORKSPACE'], 'fixed.txt').write_text('fixed')",
        ]
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp) / "runs"
            workspace = Path(tmp) / "workspace"
            workspace.mkdir()
            _git(["init", "-b", "main"], cwd=workspace)
            _git(["config", "user.name", "Test"], cwd=workspace)
            _git(["config", "user.email", "test@example.com"], cwd=workspace)
            (workspace / "fixed.txt").write_text("original", encoding="utf-8")
            _git(["add", "fixed.txt"], cwd=workspace)
            _git(["commit", "-m", "initial"], cwd=workspace)
            runner = BenchmarkRunner(
                suite="swebench-lite",
                output_dir=output_dir,
                agent_command=command,
                prepare_workspaces=True,
            )
            task = BenchmarkTask(
                id="example__repo-1",
                repo="example/repo",
                base_commit="abc123",
                problem_statement="fix it",
            )
            with mock.patch("daat_locus_benchmarks.runner.prepare_workspace", return_value=workspace):
                summary = runner.run([task])

            self.assertEqual(summary.passed, 1)
            self.assertIsNotNone(summary.predictions_path)
            predictions = Path(summary.predictions_path or "")
            self.assertTrue(predictions.exists())
            self.assertIn('"instance_id": "example__repo-1"', predictions.read_text(encoding="utf-8"))
            self.assertIn("fixed.txt", (Path(summary.results[0].patch_path or "")).read_text(encoding="utf-8"))
            self.assertEqual(summary.results[0].workspace_dir, str(workspace))


def _git(args: list[str], *, cwd: Path) -> None:
    import subprocess

    subprocess.run(["git", *args], cwd=cwd, text=True, capture_output=True, check=True)


if __name__ == "__main__":
    unittest.main()
