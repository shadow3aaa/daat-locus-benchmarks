from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from daat_locus_benchmarks.tasks import export_tasks, load_tasks


class TaskLoadingTests(unittest.TestCase):
    def test_load_builtin_smoke_task(self) -> None:
        tasks = load_tasks("local-smoke")
        self.assertEqual(len(tasks), 1)
        self.assertEqual(tasks[0].id, "local-smoke/echo-env")

    def test_load_swebench_style_jsonl(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "tasks.jsonl"
            path.write_text(
                '{"instance_id":"django__django-1","repo":"django/django","base_commit":"abc","problem_statement":"fix it","patch":"secret","test_patch":"tests"}\n',
                encoding="utf-8",
            )

            tasks = load_tasks("swebench-lite", tasks_path=path)

        self.assertEqual(tasks[0].id, "django__django-1")
        self.assertEqual(tasks[0].repo, "django/django")
        self.assertEqual(tasks[0].base_commit, "abc")
        self.assertEqual(tasks[0].problem_statement, "fix it")
        self.assertIsNone(tasks[0].expected_patch)
        self.assertNotIn("patch", tasks[0].metadata)

    def test_fetches_lite_from_huggingface_rows_api(self) -> None:
        payload = {
            "rows": [
                {
                    "row_idx": 0,
                    "row": {
                        "instance_id": "astropy__astropy-12907",
                        "repo": "astropy/astropy",
                        "base_commit": "abc",
                        "problem_statement": "fix separability",
                        "patch": "gold patch",
                        "test_patch": "gold tests",
                    },
                }
            ],
            "num_rows_total": 1,
        }
        with mock.patch("daat_locus_benchmarks.tasks._fetch_dataset_rows", return_value=payload) as fetch:
            tasks = load_tasks("swebench-lite", limit=1)

        fetch.assert_called_once()
        self.assertEqual(tasks[0].id, "astropy__astropy-12907")
        self.assertEqual(tasks[0].repo, "astropy/astropy")
        self.assertIsNone(tasks[0].expected_patch)
        self.assertEqual(tasks[0].metadata["dataset"], "princeton-nlp/SWE-bench_Lite")
        self.assertNotIn("patch", tasks[0].metadata)
        self.assertNotIn("test_patch", tasks[0].metadata)

    def test_export_tasks_writes_jsonl(self) -> None:
        payload = {
            "rows": [
                {
                    "row": {
                        "instance_id": "django__django-1",
                        "repo": "django/django",
                        "base_commit": "abc",
                        "problem_statement": "fix it",
                    }
                }
            ],
            "num_rows_total": 1,
        }
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "lite.jsonl"
            with mock.patch("daat_locus_benchmarks.tasks._fetch_dataset_rows", return_value=payload):
                tasks = export_tasks("swebench-lite", output, limit=1)

            exported = output.read_text(encoding="utf-8")

        self.assertEqual(len(tasks), 1)
        self.assertIn('"id": "django__django-1"', exported)
        self.assertIn('"dataset": "princeton-nlp/SWE-bench_Lite"', exported)


if __name__ == "__main__":
    unittest.main()
