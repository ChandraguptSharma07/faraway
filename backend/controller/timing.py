"""Deterministic sample scheduling for real-time control loops."""

from __future__ import annotations

import math


class PeriodicScheduler:
    def __init__(self, period: float, tolerance: float = 1.0e-12):
        if period <= 0.0:
            raise ValueError("control period must be positive")
        self.period = float(period)
        self.tolerance = float(tolerance)
        self.next_update: float | None = None

    def due(self, t: float) -> bool:
        now = float(t)
        if self.next_update is None:
            self.next_update = now
        if now + self.tolerance < self.next_update:
            return False
        intervals = max(
            1,
            math.floor(
                (now + self.tolerance - self.next_update) / self.period
            ) + 1,
        )
        self.next_update += intervals * self.period
        return True
