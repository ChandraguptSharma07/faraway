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
        self.position_noise = np.diag([
            (2.0 * p.displacement_noise_std) ** 2,
            (2.0 * p.displacement_noise_std) ** 2,
        ])
        # Sensor noise is tiny, but the four-state observer intentionally omits
        # flexible-wire modes. This term represents acceleration prediction error,
        # not worse accelerometer hardware.
        self.acceleration_noise = np.diag([3.0 ** 2, 3.0 ** 2])
        self.last_packet_at: float | None = None
        self.last_position_nis = 0.0
        self.last_acceleration_nis = 0.0
        self.packet_count = 0
        self.rejected_count = 0
        self.acceleration_rejected_count = 0
        self._diverged = False
        self.last_head_acceleration = 0.0

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

    def _acceleration_measurement(self, state, t, speed_ms, beyond, actuator_force):
        dx = self._dynamics(state, t, speed_ms, beyond, actuator_force)
        return np.array([dx[1], dx[3]])

    @staticmethod
    def _position_measurement(state):
        return np.array([state[2], state[0] - state[2]])

    def _update_group(self, measured, fn, noise, gate: float) -> tuple[bool, float]:
        expected = fn(self.state)
        h = self._jacobian(fn, self.state, np.array([1e-6, 1e-4, 1e-6, 1e-4]))
        innovation = measured - expected
        innovation_cov = h @ self.covariance @ h.T + noise
        try:
            solved = np.linalg.solve(innovation_cov, innovation)
            nis = float(innovation @ solved)
            gain = np.linalg.solve(innovation_cov, h @ self.covariance).T
        except np.linalg.LinAlgError:
            self._diverged = True
            return False, float("inf")
        if not np.isfinite(nis) or nis > gate:
            return False, nis
        self.state = self.state + gain @ innovation
        identity = np.eye(4)
        ikh = identity - gain @ h
        self.covariance = ikh @ self.covariance @ ikh.T + gain @ noise @ gain.T
        return True, nis

    def update(self, packet: SensorPacket, speed_ms: float, beyond: BeyondEnvelope):
        self.last_head_acceleration = packet.head_acceleration
        position = np.array([
            packet.frame_position,
            packet.head_frame_displacement,
        ])
        acceleration = np.array([
            packet.head_acceleration,
            packet.frame_acceleration,
        ])
        # A valid LVDT update is never discarded merely because the reduced process
        # model cannot reproduce a flexible-wire acceleration transient.
        latency_scale = 1.0 + (
            packet.delivered_at - packet.sampled_at
        ) / self.sensor_params.sample_period
        position_ok, self.last_position_nis = self._update_group(
            position,
            self._position_measurement,
            self.position_noise * latency_scale,
            gate=100.0,
        )
        acceleration_fn = lambda s: self._acceleration_measurement(
            s, packet.sampled_at, speed_ms, beyond, packet.actuator_force
        )
        acceleration_ok, self.last_acceleration_nis = self._update_group(
            acceleration,
            acceleration_fn,
            self.acceleration_noise * latency_scale,
            gate=25.0,
        )
        if not acceleration_ok:
            self.acceleration_rejected_count += 1
        if not position_ok:
            self.rejected_count += 1
            return
        self.last_packet_at = packet.delivered_at
        self.packet_count += 1
        self._check_finite()

    def contact_force_estimate(self, aerodynamic_force: float) -> float:
        z1, z1d, z2, z2d = self.state
        force = (
            aerodynamic_force
            - self.panto.m1 * self.last_head_acceleration
            - self.panto.r1 * (z1d - z2d)
            - self.panto.k1 * (z1 - z2)
        )
        return float(np.clip(force, 0.0, 500.0))

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
            "nis": round(self.last_position_nis, 3),
            "acceleration_nis": round(self.last_acceleration_nis, 3),
            "covariance_trace": round(float(np.trace(self.covariance)), 8),
            "packets_accepted": self.packet_count,
            "packets_rejected": self.rejected_count,
            "acceleration_updates_rejected": self.acceleration_rejected_count,
        }
