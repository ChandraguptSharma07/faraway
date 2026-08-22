"""Bounded active-pantograph actuator used by the live simulation.

The 7 Hz response target is inferred from RTRI vibration-test evidence for the
effective impedance-control range; it is not a manufacturer actuator specification.
Transport delay and force/rate limits remain explicit assumptions.
Reference: https://doi.org/10.2219/rtriqr.53.28
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class ActuatorParams:
    response_hz: float = 7.0
    transport_delay: float = 4.0e-3
    force_limit: float = 90.0
    force_rate_limit: float = 4_000.0

    @property
    def time_constant(self) -> float:
        return 1.0 / (2.0 * np.pi * self.response_hz)


ACTUATOR_PROVENANCE = {
    "response_hz": "published-experimental-effective-control-range",
    "transport_delay": "assumed-control-cycle-delay",
    "force_limit": "assumed-existing-training-envelope",
    "force_rate_limit": "assumed-derived-from-force-and-bandwidth",
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
