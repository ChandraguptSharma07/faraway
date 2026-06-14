"""PINN-MPC controller — the predictive control loop AROUND the PINN predictor.

This is NOT the PINN. Each control step it asks the PINN to predict the contact force
a horizon H ahead for a set of candidate counter-forces, then picks the candidate that
keeps the predicted contact force closest to the setpoint (with a small control-effort
and rate penalty). Short-horizon receding control — simple and honest.

The selected counter-force is applied to the collector head (same channel as the
aerodynamic force), emulating an active actuator.
"""

from __future__ import annotations

import time

import numpy as np

from backend.pinn.data import _wire_features
from backend.pinn.predict import PINNPredictor
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
        n_candidates: int = 41,
        control_period: float = 2.0e-3,
        w_effort: float = 1.0e-4,
        w_rate: float = 5.0e-4,
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

        self._last_fc = 0.0
        self._last_t = -1e9
        self._held = 0.0
        self.last_latency_ms = 0.0  # inference time of the most recent re-optimisation

    def __call__(self, t: float, state, force: float) -> float:
        # Receding-horizon: only re-optimise every control_period; hold otherwise.
        if t - self._last_t < self.control_period:
            return self._held
        self._last_t = t

        fa = self.dist.aero_force(self.speed_ms, self.beyond)
        wf = _wire_features(self.dist, t, self.speed_ms, self.beyond)
        t0 = time.perf_counter()
        pred_force = self.pred.predict_force_candidates(state, self.candidates, fa, wf)
        self.last_latency_ms = 1e3 * (time.perf_counter() - t0)

        cost = (
            (pred_force - self.setpoint) ** 2
            + self.w_effort * self.candidates ** 2
            + self.w_rate * (self.candidates - self._last_fc) ** 2
        )
        best = float(self.candidates[int(np.argmin(cost))])
        self._last_fc = best
        self._held = best
        return best
