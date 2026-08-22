"""Hybrid actuator-aware PINN-MPC.

The actuator remains explicit and auditable. For every candidate command, its
bounded delayed force trajectory is previewed first. The existing PINN then rolls
the pantograph state through that applied-force trajectory. This avoids teaching
hardware assumptions to the pantograph surrogate and prevents the instantaneous-
actuation fiction used by the idealized baseline.
"""

from __future__ import annotations

from collections import deque
import time

import numpy as np

from backend.controller.actuator import ForceActuator
from backend.pinn.data import _wire_features
from backend.pinn.predict import PINNPredictor
from backend.sim.disturbance import Disturbance
from backend.sim.parameters import BeyondEnvelope


class ActuatorAwarePINNMPC:
    def __init__(
        self,
        predictor: PINNPredictor,
        actuator: ForceActuator,
        dist: Disturbance,
        speed_ms: float,
        beyond: BeyondEnvelope,
        setpoint: float = 115.0,
        n_candidates: int = 21,
        rollout_steps: int = 18,
        control_period: float = 10.0e-3,
        w_effort: float = 2.0e-4,
        w_rate: float = 1.5e-3,
    ):
        self.pred = predictor
        self.actuator = actuator
        self.dist = dist
        self.speed_ms = speed_ms
        self.beyond = beyond
        self.setpoint = setpoint
        self.rollout_steps = rollout_steps
        self.control_period = max(control_period, predictor.H)
        limit = actuator.params.force_limit
        self.candidates = np.linspace(-limit, limit, n_candidates).astype(np.float32)
        self.w_effort = w_effort
        self.w_rate = w_rate
        self._last_command = 0.0
        self._last_t = -1e9
        self._held = 0.0
        self.last_latency_ms = 0.0
        self._latencies = deque(maxlen=500)
        self._deadline_misses = deque(maxlen=500)

    def __call__(self, t: float, state, _force: float) -> float:
        if t - self._last_t < self.control_period:
            return self._held
        self._last_t = t
        started = time.perf_counter()

        applied = self.actuator.preview_profiles(
            self.candidates, self.pred.H, self.rollout_steps
        )
        states = np.repeat(
            np.asarray(state, dtype=np.float32)[None, :],
            len(self.candidates),
            axis=0,
        )
        tracking_cost = np.zeros(len(self.candidates), dtype=np.float64)
        fa = self.dist.aero_force(self.speed_ms, self.beyond)
        for step in range(self.rollout_steps):
            future_t = t + step * self.pred.H
            wire = _wire_features(self.dist, future_t, self.speed_ms, self.beyond)
            states, predicted_force = self.pred.predict_state_candidates(
                states, applied[step], fa, wire
            )
            # Later samples matter more: early samples are mostly fixed by delay.
            weight = 0.5 + (step + 1) / self.rollout_steps
            tracking_cost += weight * (predicted_force - self.setpoint) ** 2

        cost = (
            tracking_cost
            + self.w_effort * self.candidates ** 2
            + self.w_rate * (self.candidates - self._last_command) ** 2
        )
        best = float(self.candidates[int(np.argmin(cost))])
        self.last_latency_ms = 1e3 * (time.perf_counter() - started)
        self._latencies.append(self.last_latency_ms)
        self._deadline_misses.append(
            self.last_latency_ms > 1e3 * self.control_period
        )
        self._last_command = best
        self._held = best
        return best

    def timing_metrics(self) -> dict:
        if not self._latencies:
            return {
                "latency_p95_ms": 0.0,
                "latency_p99_ms": 0.0,
                "deadline_miss_pct": 0.0,
                "samples": 0,
            }
        values = np.fromiter(self._latencies, dtype=float)
        return {
            "latency_p95_ms": float(np.percentile(values, 95)),
            "latency_p99_ms": float(np.percentile(values, 99)),
            "deadline_miss_pct": 100.0 * float(np.mean(self._deadline_misses)),
            "samples": len(values),
        }

    def reset_timing(self) -> None:
        self._latencies.clear()
        self._deadline_misses.clear()
