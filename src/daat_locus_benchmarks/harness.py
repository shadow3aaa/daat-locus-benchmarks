from __future__ import annotations

import subprocess
from pathlib import Path


def build_harness_command(
    *,
    predictions_path: Path,
    dataset_name: str,
    split: str,
    run_id: str,
    max_workers: int,
) -> list[str]:
    """Build the official SWE-bench harness evaluation command."""

    return [
        "python",
        "-m",
        "swebench.harness.run_evaluation",
        "--dataset_name",
        dataset_name,
        "--split",
        split,
        "--predictions_path",
        str(predictions_path),
        "--max_workers",
        str(max_workers),
        "--run_id",
        run_id,
    ]


def run_harness(command: list[str]) -> subprocess.CompletedProcess[str]:
    """Run the official SWE-bench harness command without a shell wrapper."""

    return subprocess.run(command, text=True, check=False)
