"""Bounded pneumatic frame actuator used by the live simulation.

Test-rig baseline, not railway-certified hardware:
- SMC VER2000 proportional valve: 40 ms published response time.
- SMC MQQ/MQM 25 mm low-friction cylinder: 490.9 mm² cap-side area; the
  selected 0.2 MPa differential-pressure cap gives 98.2 N theoretical force.
- RTRI active-pantograph experiments place a pneumatic cylinder in parallel with
  the raising mechanism and apply force to the articulated frame.

The 4 ms digital transport delay remains an explicit assumption pending measurement.
Sources: https://doi.org/10.2219/rtriqr.53.28
         https://www.smcworld.com/catalog/BEST-5-5-en/mpv/5-p0892-0898-ver_en/data/5-p0892-0898-ver_en.pdf
         https://www.smcworld.com/catalog/en/actuator/MQQ-MQM-MQP-E/6-2-3-p0317-0344-mq_en/data/6-2-3-p0317-0344-mq_en.pdf
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class ActuatorParams:
    response_time: float = 40.0e-3
    transport_delay: float = 4.0e-3
    force_limit: float = 98.2
    force_rate_limit: float = 2_455.0

    @property
    def time_constant(self) -> float:
        # Conservative first-order interpretation of the published valve response.
        return self.response_time

    @property
    def response_hz(self) -> float:
        return 1.0 / (2.0 * np.pi * self.response_time)


ACTUATOR_PROVENANCE = {
    "response_time": "published-smc-ver2000-no-load-response",
    "transport_delay": "assumed-control-cycle-delay",
    "force_limit": "derived-smc-mqq25-area-at-selected-0.2mpa-differential",
    "force_rate_limit": "derived-force-limit-over-published-response-time",
}

ACTUATOR_BASELINE = {
    "status": "DATASHEET_BASELINE_NOT_IDENTIFIED",
    "mounting": "ARTICULATED_FRAME",
    "valve": "SMC VER2000",
    "cylinder": "SMC MQQ/MQM 25 mm low-friction",
    "valve_response_ms": 40.0,
    "piston_area_mm2": 490.9,
    "selected_pressure_differential_MPa": 0.2,
    "railway_qualified": False,
}


class ForceActuator:
    """Transport delay + first-order force response + configured bounds."""

    def __init__(self, dt: float, params: ActuatorParams | None = None):
        if dt <= 0.0:
            raise ValueError("dt must be positive")
        self.dt = dt
        self.params = params or ActuatorParams()
        self.force = 0.0
        self.command = 0.0
        self._delay_steps = max(0, int(round(self.params.transport_delay / dt)))
        self._queue = deque([0.0] * self._delay_steps)

    def step(self, command: float) -> float:
        p = self.params
        self.command = float(np.clip(command, -p.force_limit, p.force_limit))
        if self._delay_steps:
            delayed = self._queue.popleft()
            self._queue.append(self.command)
        else:
            delayed = self.command
        desired_rate = (delayed - self.force) / p.time_constant
        rate = float(np.clip(desired_rate, -p.force_rate_limit, p.force_rate_limit))
        self.force = float(np.clip(
            self.force + self.dt * rate,
            -p.force_limit,
            p.force_limit,
        ))
        return self.force

    def preview_candidates(self, commands: np.ndarray, horizon: float) -> np.ndarray:
        """Approximate force available by the PINN horizon for candidate scoring."""
        commands = np.clip(
            np.asarray(commands, dtype=np.float32),
            -self.params.force_limit,
            self.params.force_limit,
        )
        effective_time = max(0.0, horizon - self.params.transport_delay)
        if effective_time == 0.0:
            return np.full_like(commands, self.force)
        response = 1.0 - np.exp(-effective_time / self.params.time_constant)
        delta = (commands - self.force) * response
        max_delta = self.params.force_rate_limit * effective_time
        return (self.force + np.clip(delta, -max_delta, max_delta)).astype(np.float32)

    def preview_profiles(
        self,
        commands: np.ndarray,
        interval: float,
        n_intervals: int,
    ) -> np.ndarray:
        """Mean applied force per interval without mutating the live actuator.

        Each candidate command is held across the preview. The calculation uses the
        same delay queue, first-order response, rate limit, and force limit as step().
        Shape is ``(n_intervals, n_candidates)``.
        """
        if interval <= 0.0 or n_intervals < 1:
            raise ValueError("preview interval and count must be positive")
        substeps = max(1, int(round(interval / self.dt)))
        commands = np.clip(
            np.atleast_1d(np.asarray(commands, dtype=np.float64)),
            -self.params.force_limit,
            self.params.force_limit,
        )
        forces = np.full(commands.shape, self.force, dtype=np.float64)
        queue = np.tile(np.asarray(self._queue, dtype=np.float64), (len(commands), 1))
        profile = np.empty((n_intervals, len(commands)), dtype=np.float32)
        p = self.params

        for block in range(n_intervals):
            total = np.zeros_like(forces)
            for _ in range(substeps):
                if self._delay_steps:
                    delayed = queue[:, 0].copy()
                    queue[:, :-1] = queue[:, 1:]
                    queue[:, -1] = commands
                else:
                    delayed = commands
                desired_rate = (delayed - forces) / p.time_constant
                rate = np.clip(desired_rate, -p.force_rate_limit, p.force_rate_limit)
                forces = np.clip(
                    forces + self.dt * rate,
                    -p.force_limit,
                    p.force_limit,
                )
                total += forces
            profile[block] = total / substeps
        return profile
