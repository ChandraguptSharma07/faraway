"""PINN-MPC controller — the predictive control loop AROUND the PINN predictor.

This is NOT the PINN. Each control step it asks the PINN to predict the contact force
a horizon H ahead for a set of candidate counter-forces, then picks the candidate that
keeps the predicted contact force closest to the setpoint (with a small control-effort
and rate penalty). Short-horizon receding control — simple and honest.

The selected force is applied to the articulated frame by the plant model, matching
the pneumatic frame-actuation layout used in RTRI experiments.
"""

from __future__ import annotations

from collections import deque
import time

import numpy as np

from backend.pinn.data import _wire_features
from backend.pinn.predict import PINNPredictor
from backend.controller.selection import minimum_effort_near_optimum
from backend.sim.disturbance import Disturbance
from backend.sim.parameters import BeyondEnvelope


class PINNMPCController:
    def __init__(
        self,
        predictor: PINNPredictor,
        dist: Disturbance,
        speed_ms: float,
        beyond: BeyondEnvelope,
        setpoint: float = 115.0,
        f_max: float = 90.0,
        n_candidates: int = 21,
        control_period: float = 4.0e-3,
        w_effort: float = 1.0e-4,
        w_rate: float = 5.0e-4,
        candidate_force_fn=None,
        force_resolution: float = 0.10,
    ):
        self.pred = predictor
        self.dist = dist
        self.speed_ms = speed_ms
        self.beyond = beyond
        self.setpoint = setpoint
        self.f_max = f_max
        self.candidates = np.linspace(-f_max, f_max, n_candidates).astype(np.float32)
        self.control_period = control_period
        self.w_effort = w_effort
        self.w_rate = w_rate
        self.candidate_force_fn = candidate_force_fn
        if force_resolution <= 0.0:
            raise ValueError("force_resolution must be positive")
        self.cost_tie_tolerance = force_resolution ** 2

        self._last_fc = 0.0
        self._last_t = -1e9
        self._held = 0.0
        self.last_latency_ms = 0.0  # full time of the latest control update
        self._latencies = deque(maxlen=500)
        self._deadline_misses = deque(maxlen=500)

    def __call__(self, t: float, state, force: float) -> float:
        # Receding-horizon: only re-optimise every control_period; hold otherwise.
        if t - self._last_t < self.control_period:
            return self._held
        self._last_t = t

        t0 = time.perf_counter()
        fa = self.dist.aero_force(self.speed_ms, self.beyond)
        wf = _wire_features(self.dist, t, self.speed_ms, self.beyond)
        applied_candidates = (
            self.candidates
            if self.candidate_force_fn is None
            else self.candidate_force_fn(self.candidates, self.pred.H)
        )
        pred_force = self.pred.predict_force_candidates(state, applied_candidates, fa, wf)

        cost = (
            (pred_force - self.setpoint) ** 2
            + self.w_effort * self.candidates ** 2
            + self.w_rate * (self.candidates - self._last_fc) ** 2
        )
        best_index = minimum_effort_near_optimum(
            cost,
            self.candidates,
            self.cost_tie_tolerance,
            self._last_fc,
        )
        best = float(self.candidates[best_index])
        self.last_latency_ms = 1e3 * (time.perf_counter() - t0)
        self._latencies.append(self.last_latency_ms)
        self._deadline_misses.append(self.last_latency_ms > 1e3 * self.control_period)
        self._last_fc = best
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
