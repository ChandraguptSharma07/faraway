"""Four-state extended Kalman filter for the two-mass pantograph model."""

from __future__ import annotations

import numpy as np

from backend.controller.sensors import SensorPacket, SensorParams
from backend.sim.parameters import BeyondEnvelope, PantographParams
from backend.sim.solver import deriv


class PantographEKF:
    def __init__(
        self,
        initial_state: np.ndarray,
        dt: float,
        dist,
        panto: PantographParams,
        sensor_params: SensorParams,
    ):
        self.state = np.asarray(initial_state, dtype=float).copy()
        self.dt = dt
        self.dist = dist
        self.panto = panto
        self.sensor_params = sensor_params
        self.covariance = np.diag([2e-6, 2e-3, 2e-6, 2e-3])
        self.process_noise = np.diag([1e-10, 2e-4, 1e-10, 2e-4])
        p = sensor_params
        self.measurement_noise = np.diag([
            (2.0 * p.displacement_noise_std) ** 2,
            (2.0 * p.displacement_noise_std) ** 2,
            (4.0 * p.acceleration_noise_std) ** 2,
            (4.0 * p.acceleration_noise_std) ** 2,
        ])
        self.last_packet_at: float | None = None
        self.last_nis = 0.0
        self.packet_count = 0
        self.rejected_count = 0
        self._diverged = False

    def _dynamics(self, state, t, speed_ms, beyond, actuator_force):
        return deriv(
            state, t, speed_ms, self.dist, self.panto, beyond, actuator_force
        )[0]

    @staticmethod
    def _jacobian(fn, x: np.ndarray, eps: np.ndarray) -> np.ndarray:
        base = fn(x)
        jac = np.empty((len(base), len(x)))
        for i, step in enumerate(eps):
            shifted = x.copy()
            shifted[i] += step
            jac[:, i] = (fn(shifted) - base) / step
        return jac

    def predict(self, t: float, speed_ms: float, beyond: BeyondEnvelope, actuator_force: float):
        x = self.state
        fn = lambda s: self._dynamics(s, t, speed_ms, beyond, actuator_force)
        f = fn(x)
        a = np.eye(4) + self.dt * self._jacobian(
            fn, x, np.array([1e-6, 1e-4, 1e-6, 1e-4])
        )
        self.state = x + self.dt * f
        self.covariance = a @ self.covariance @ a.T + self.process_noise
        self._check_finite()

    def _measurement(self, state, t, speed_ms, beyond, actuator_force):
        dx = self._dynamics(state, t, speed_ms, beyond, actuator_force)
        return np.array([state[2], state[0] - state[2], dx[1], dx[3]])

    def update(self, packet: SensorPacket, speed_ms: float, beyond: BeyondEnvelope):
        measured = np.array([
            packet.frame_position,
            packet.head_frame_displacement,
            packet.head_acceleration,
            packet.frame_acceleration,
        ])
        # The short packet latency is represented by evaluating the measurement at
        # its timestamp and inflating R below. A hardware implementation should use
        # timestamped fixed-lag replay once acquisition timing is identified.
        fn = lambda s: self._measurement(
            s, packet.sampled_at, speed_ms, beyond, packet.actuator_force
        )
        expected = fn(self.state)
        h = self._jacobian(fn, self.state, np.array([1e-6, 1e-4, 1e-6, 1e-4]))
        latency_scale = 1.0 + (
            packet.delivered_at - packet.sampled_at
        ) / self.sensor_params.sample_period
        r = self.measurement_noise * latency_scale
        innovation = measured - expected
        innovation_cov = h @ self.covariance @ h.T + r
        try:
            solved = np.linalg.solve(innovation_cov, innovation)
            self.last_nis = float(innovation @ solved)
            gain = np.linalg.solve(innovation_cov, h @ self.covariance).T
        except np.linalg.LinAlgError:
            self._diverged = True
            self.rejected_count += 1
            return

        # Reject grossly impossible packets instead of injecting them into control.
        # A real aerodynamic gust is a large coherent two-accelerometer innovation,
        # so the gate is intentionally wide. Hardware plausibility/rate checks must
        # precede this statistical gate on the eventual acquisition device.
        if not np.isfinite(self.last_nis) or self.last_nis > 1_000.0:
            self.rejected_count += 1
            return
        self.state = self.state + gain @ innovation
        identity = np.eye(4)
        ikh = identity - gain @ h
        self.covariance = ikh @ self.covariance @ ikh.T + gain @ r @ gain.T
        self.last_packet_at = packet.delivered_at
        self.packet_count += 1
        self._check_finite()

    def _check_finite(self):
        if (
            not np.all(np.isfinite(self.state))
            or not np.all(np.isfinite(self.covariance))
            or np.max(np.abs(self.state[[0, 2]])) > 0.5
            or np.trace(self.covariance) > 10.0
        ):
            self._diverged = True

    def health(self, t: float) -> tuple[bool, str]:
        if self._diverged:
            return False, "ESTIMATOR_DIVERGED"
        if self.packet_count < 3:
            return False, "ESTIMATOR_STARTING"
        age = t - (self.last_packet_at if self.last_packet_at is not None else 0.0)
        if age > self.sensor_params.stale_after:
            return False, "SENSOR_DATA_STALE"
        return True, "HEALTHY"

    def telemetry(self, t: float) -> dict:
        healthy, reason = self.health(t)
        age = None if self.last_packet_at is None else max(0.0, t - self.last_packet_at)
        return {
            "status": "HEALTHY" if healthy else "FALLBACK",
            "reason": reason,
            "packet_age_ms": None if age is None else round(1e3 * age, 3),
            "nis": round(self.last_nis, 3),
            "covariance_trace": round(float(np.trace(self.covariance)), 8),
            "packets_accepted": self.packet_count,
            "packets_rejected": self.rejected_count,
        }
