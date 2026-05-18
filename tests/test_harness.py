from __future__ import annotations

import unittest
from pathlib import Path

from daat_locus_benchmarks.harness import build_harness_command


class HarnessTests(unittest.TestCase):
    def test_build_harness_command(self) -> None:
        command = build_harness_command(
            predictions_path=Path("predictions/lite-smoke.jsonl"),
            dataset_name="princeton-nlp/SWE-bench_Lite",
            split="test",
            run_id="daat-lite-smoke",
            max_workers=1,
        )

        self.assertEqual(command[:3], ["python", "-m", "swebench.harness.run_evaluation"])
        self.assertIn("--predictions_path", command)
        self.assertIn("predictions/lite-smoke.jsonl", command)
        self.assertIn("princeton-nlp/SWE-bench_Lite", command)


if __name__ == "__main__":
    unittest.main()
