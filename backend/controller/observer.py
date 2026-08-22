"""Four-state extended Kalman filter for the two-mass pantograph model."""

from __future__ import annotations

import numpy as np

from backend.controller.sensors import SensorPacket, SensorParams
from backend.sim.parameters import BeyondEnvelope, PantographParams
from backend.sim.solver import deriv


class PantographEKF:
    """Extended Kalman Filter (EKF) for a two-mass pantograph model.

    This observer estimates the state of the pantograph based on position
    and acceleration measurements. It uses a reduced 4-state model,
    intentionally omitting flexible wire modes.
    """
    def __init__(
        self,
        initial_state: np.ndarray,
        dt: float,
        dist,
        panto: PantographParams,
        sensor_params: SensorParams,
    ):
        """Initializes the Extended Kalman Filter.

        Args:
            initial_state (np.ndarray): The initial state estimate of the pantograph.
            dt (float): The base time step for predictions in seconds.
            dist (Disturbance): The environment disturbance model.
            panto (PantographParams): The nominal pantograph parameters.
            sensor_params (SensorParams): The sensor noise and configuration parameters.
        """
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
        """Computes the continuous-time dynamics derivative.

        Args:
            state (np.ndarray): The current state vector.
            t (float): The current simulation time in seconds.
            speed_ms (float): The train speed in meters per second.
            beyond (BeyondEnvelope): Beyond-envelope parameters.
            actuator_force (float): The applied actuator force in Newtons.

        Returns:
            np.ndarray: The state derivative.
        """
        return deriv(
            state, t, speed_ms, self.dist, self.panto, beyond, actuator_force
        )[0]

    @staticmethod
    def _jacobian(fn, x: np.ndarray, eps: np.ndarray) -> np.ndarray:
        """Computes the Jacobian matrix numerically using finite differences.

        Args:
            fn (callable): The vector-valued function to differentiate.
            x (np.ndarray): The point at which to evaluate the Jacobian.
            eps (np.ndarray): The step sizes for finite differences.

        Returns:
            np.ndarray: The numerically evaluated Jacobian matrix.
        """
        base = fn(x)
        jac = np.empty((len(base), len(x)))
        for i, step in enumerate(eps):
            shifted = x.copy()
            shifted[i] += step
            jac[:, i] = (fn(shifted) - base) / step
        return jac

    def predict(self, t: float, speed_ms: float, beyond: BeyondEnvelope, actuator_force: float):
        """Advances the state estimate forward in time by one prediction step.

        Args:
            t (float): The current simulation time in seconds.
            speed_ms (float): The train speed in meters per second.
            beyond (BeyondEnvelope): Beyond-envelope parameters.
            actuator_force (float): The applied actuator force in Newtons.
        """
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
        """Computes the expected acceleration measurement from the given state.

        Args:
            state (np.ndarray): The state vector.
            t (float): The measurement time in seconds.
            speed_ms (float): The train speed in meters per second.
            beyond (BeyondEnvelope): Beyond-envelope parameters.
            actuator_force (float): The applied actuator force in Newtons.

        Returns:
            np.ndarray: The expected acceleration vector.
        """
        dx = self._dynamics(state, t, speed_ms, beyond, actuator_force)
        return np.array([dx[1], dx[3]])

    @staticmethod
    def _position_measurement(state):
        """Computes the expected position measurement from the given state.

        Args:
            state (np.ndarray): The state vector.

        Returns:
            np.ndarray: The expected position measurement vector.
        """
        return np.array([state[2], state[0] - state[2]])

    def _update_group(self, measured, fn, noise, gate: float) -> tuple[bool, float]:
        """Performs an EKF measurement update step for a specific group of sensors.

        Args:
            measured (np.ndarray): The actual measurement values.
            fn (callable): A function returning the expected measurements for a state.
            noise (np.ndarray): The measurement noise covariance matrix.
            gate (float): The threshold for the Normalized Innovation Squared (NIS).
                          Updates exceeding this gate are rejected as outliers.

        Returns:
            tuple: A boolean indicating whether the update was accepted, and the NIS value.
        """
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
        """Processes a new sensor packet and updates the state estimate.

        Args:
            packet (SensorPacket): The incoming sensor measurements.
            speed_ms (float): The train speed in meters per second.
            beyond (BeyondEnvelope): Beyond-envelope parameters.
        """
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
        """Estimates the contact force between the pantograph and the wire.

        Args:
            aerodynamic_force (float): The aerodynamic force on the pantograph in Newtons.

        Returns:
            float: The estimated contact force in Newtons.
        """
        z1, z1d, z2, z2d = self.state
        force = (
            aerodynamic_force
            - self.panto.m1 * self.last_head_acceleration
            - self.panto.r1 * (z1d - z2d)
            - self.panto.k1 * (z1 - z2)
        )
        return float(np.clip(force, 0.0, 500.0))

    def _check_finite(self):
        """Checks if the estimator state is finite and within reasonable bounds.

        Marks the estimator as diverged if the state or covariance contains non-finite
        values, or if they grow too large.
        """
        if (
            not np.all(np.isfinite(self.state))
            or not np.all(np.isfinite(self.covariance))
            or np.max(np.abs(self.state[[0, 2]])) > 0.5
            or np.trace(self.covariance) > 10.0
        ):
            self._diverged = True

    def health(self, t: float) -> tuple[bool, str]:
        """Evaluates the health and reliability of the estimator.

        Args:
            t (float): The current simulation time in seconds.

        Returns:
            tuple: A boolean indicating whether the estimator is healthy,
                   and a string describing the health status reason.
        """
        if self._diverged:
            return False, "ESTIMATOR_DIVERGED"
        if self.packet_count < 3:
            return False, "ESTIMATOR_STARTING"
        age = t - (self.last_packet_at if self.last_packet_at is not None else 0.0)
        if age > self.sensor_params.stale_after:
            return False, "SENSOR_DATA_STALE"
        return True, "HEALTHY"

    def telemetry(self, t: float) -> dict:
        """Collects telemetry data on the estimator's performance and status.

        Args:
            t (float): The current simulation time in seconds.

        Returns:
            dict: A dictionary of telemetry metrics.
        """
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
