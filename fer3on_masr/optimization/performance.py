from __future__ import annotations

import time
from dataclasses import dataclass, field


@dataclass(slots=True)
class TimedStep:
    name: str
    started_at: float = field(default_factory=time.perf_counter)
    ended_at: float | None = None

    def stop(self) -> None:
        self.ended_at = time.perf_counter()

    @property
    def duration_ms(self) -> float:
        end = self.ended_at if self.ended_at is not None else time.perf_counter()
        return round((end - self.started_at) * 1000.0, 3)


class PerformanceOptimizer:
    def __init__(self) -> None:
        self.steps: list[TimedStep] = []

    def start(self, name: str) -> TimedStep:
        step = TimedStep(name=name)
        self.steps.append(step)
        return step

    def summary(self) -> dict[str, float]:
        return {step.name: step.duration_ms for step in self.steps}
