from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

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


if __name__ == "__main__":
    unittest.main()
