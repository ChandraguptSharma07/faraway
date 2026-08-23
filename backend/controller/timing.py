"""Deterministic sample scheduling for real-time control loops."""

from __future__ import annotations

import math


class PeriodicScheduler:
    """Schedules periodic updates for deterministic control loops.
    
    This scheduler ensures that control loops execute at regular intervals,
    accounting for small timing variations and missed deadlines.
    
    Attributes:
        period (float): The target control period in seconds.
        tolerance (float): The allowed timing tolerance in seconds.
        next_update (float | None): The scheduled time for the next update.
    """

    def __init__(self, period: float, tolerance: float = 1.0e-12):
        """Initializes the PeriodicScheduler.
        
        Args:
            period (float): The time between scheduled updates in seconds.
            tolerance (float, optional): The timing tolerance for the update in seconds.
                Defaults to 1.0e-12.
                
        Raises:
            ValueError: If the period is not greater than zero.
        """
        if period <= 0.0:
            raise ValueError("control period must be positive")
        self.period = float(period)
        self.tolerance = float(tolerance)
        self.next_update: float | None = None

    def due(self, t: float) -> bool:
        """Determines if an update is due at the given time.
        
        If the update is due, advances the next scheduled update time by the
        appropriate number of intervals to catch up to or pass the current time.
        
        Args:
            t (float): The current time in seconds.
            
        Returns:
            bool: True if an update should be performed now, False otherwise.
        """
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
