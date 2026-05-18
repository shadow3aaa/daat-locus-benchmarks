from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .models import BenchmarkTask
from .reporting import write_jsonl


@dataclass(frozen=True)
class Prediction:
    instance_id: str
    model_name_or_path: str
    model_patch: str

    def to_dict(self) -> dict[str, str]:
        return {
            "instance_id": self.instance_id,
            "model_name_or_path": self.model_name_or_path,
            "model_patch": self.model_patch,
        }


def prediction_from_patch(task: BenchmarkTask, patch: str, *, model_name: str) -> Prediction:
    return Prediction(instance_id=task.id, model_name_or_path=model_name, model_patch=patch)


def write_predictions(path: Path, predictions: list[Prediction]) -> None:
    write_jsonl(path, (prediction.to_dict() for prediction in predictions))
