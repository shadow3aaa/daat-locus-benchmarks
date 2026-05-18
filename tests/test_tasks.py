from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from daat_locus_benchmarks.tasks import load_tasks


class TaskLoadingTests(unittest.TestCase):
    def test_load_builtin_smoke_task(self) -> None:
        tasks = load_tasks("local-smoke")
        self.assertEqual(len(tasks), 1)
        self.assertEqual(tasks[0].id, "local-smoke/echo-env")

    def test_load_swebench_style_jsonl(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "tasks.jsonl"
            path.write_text(
                '{"instance_id":"django__django-1","repo":"django/django","base_commit":"abc","problem_statement":"fix it"}\n',
                encoding="utf-8",
            )

            tasks = load_tasks("swebench-lite", tasks_path=path)

        self.assertEqual(tasks[0].id, "django__django-1")
        self.assertEqual(tasks[0].repo, "django/django")
        self.assertEqual(tasks[0].base_commit, "abc")
        self.assertEqual(tasks[0].problem_statement, "fix it")


if __name__ == "__main__":
    unittest.main()
