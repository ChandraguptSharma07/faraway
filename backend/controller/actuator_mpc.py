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
from backend.controller.selection import minimum_effort_near_optimum
from backend.controller.timing import PeriodicScheduler
from backend.pinn.data import _wire_features
from backend.pinn.predict import PINNPredictor
from backend.sim.parameters import BeyondEnvelope


DEPLOYED_CONTROL_PERIOD = 18.0e-3
DEPLOYED_COMMAND_LIMIT = 25.0
DEPLOYED_CANDIDATES = 21
DEPLOYED_ROLLOUT_STEPS = 18


class ActuatorAwarePINNMPC:
    """Hybrid actuator-aware Physics-Informed Neural Network Model Predictive Controller.

    Integrates a PINN predictor with an explicit actuator model to preview delayed
    force trajectories and roll out pantograph states, optimizing control effort and tracking error.
    """

    def __init__(
        self,
        predictor: PINNPredictor,
        actuator: ForceActuator,
        dist,
        speed_ms: float,
        beyond: BeyondEnvelope,
        setpoint: float = 115.0,
        n_candidates: int = 21,
        rollout_steps: int = 18,
        control_period: float = 10.0e-3,
        w_effort: float = 2.0e-4,
        w_rate: float = 1.5e-3,
        wire_estimate=None,
        w_wave_position: float = 1.0,
        w_wave_velocity: float = 2.0e-3,
        command_limit: float | None = None,
        force_resolution: float = 0.10,
        force_bias_time_constant: float = 0.25,
        force_bias_limit: float = 10.0,
        force_bias_command_gain: float = 0.5,
    ):
        """Initializes the PINN-MPC controller with the given predictive models and weights.

        Args:
            predictor (PINNPredictor): The physics-informed neural network used for state prediction.
            actuator (ForceActuator): The actuator model used to preview physical force responses.
            dist: Disturbance model for aerodynamic and mechanical interactions.
            speed_ms (float): Train speed in meters per second.
            beyond (BeyondEnvelope): Parameters extending the simulation envelope.
            setpoint (float, optional): Target contact force in Newtons. Defaults to 115.0.
            n_candidates (int, optional): Number of discrete force commands to evaluate. Defaults to 21.
            rollout_steps (int, optional): Number of prediction steps in the MPC horizon. Defaults to 18.
            control_period (float, optional): The time interval between control updates in seconds. Defaults to 10.0e-3.
            w_effort (float, optional): Penalty weight for absolute control effort. Defaults to 2.0e-4.
            w_rate (float, optional): Penalty weight for the rate of change of the command. Defaults to 1.5e-3.
            wire_estimate (optional): An estimator for the catenary wire state dynamics. Defaults to None.
            w_wave_position (float, optional): Penalty weight for wave displacement. Defaults to 1.0.
            w_wave_velocity (float, optional): Penalty weight for wave velocity. Defaults to 2.0e-3.
            command_limit (float | None, optional): Explicit limit on command force, defaults to actuator limits if None.
            force_resolution (float, optional): Resolution threshold for considering costs equivalent. Defaults to 0.10.
            force_bias_time_constant (float, optional): Time constant for the integral force bias correction. Defaults to 0.25.
            force_bias_limit (float, optional): Maximum allowed integral force bias correction. Defaults to 10.0.
            force_bias_command_gain (float, optional): Feedforward gain for the force bias correction. Defaults to 0.5.

        Raises:
            ValueError: If command_limit, force_resolution, or force bias dynamics are invalid.
        """
        self.pred = predictor
        self.actuator = actuator
        self.dist = dist
        self.speed_ms = speed_ms
        self.beyond = beyond
        self.setpoint = setpoint
        self.rollout_steps = rollout_steps
        self.control_period = max(control_period, predictor.H)
        limit = min(
            actuator.params.force_limit,
            actuator.params.force_limit if command_limit is None else command_limit,
        )
        if limit <= 0.0:
            raise ValueError("command_limit must be positive")
        self.command_limit = float(limit)
        self.candidates = np.linspace(-limit, limit, n_candidates).astype(np.float32)
        self.w_effort = w_effort
        self.w_rate = w_rate
        self.wire_estimate = wire_estimate
        self.w_wave_position = w_wave_position
        self.w_wave_velocity = w_wave_velocity
        if force_resolution <= 0.0:
            raise ValueError("force_resolution must be positive")
        if (
            force_bias_time_constant <= 0.0
            or force_bias_limit < 0.0
            or force_bias_command_gain < 0.0
        ):
            raise ValueError("force-bias dynamics must be positive and bounded")
        tracking_weight_sum = sum(
            0.5 + (step + 1) / rollout_steps
            for step in range(rollout_steps)
        )
        self.cost_tie_tolerance = tracking_weight_sum * force_resolution ** 2
        self.force_bias_alpha = 1.0 - np.exp(
            -self.control_period / force_bias_time_constant
        )
        self.force_bias_limit = float(force_bias_limit)
        self.force_bias_command_gain = float(force_bias_command_gain)
        self.force_bias_correction = 0.0
        self._last_command = 0.0
        self._scheduler = PeriodicScheduler(self.control_period)
        self._held = 0.0
        self.last_latency_ms = 0.0
        self._latencies = deque(maxlen=500)
        self._deadline_misses = deque(maxlen=500)

    def __call__(self, t: float, state, measured_force: float | None) -> float:
        """Evaluates the optimal control action for the current state and time.

        Args:
            t (float): Current simulation or physical time in seconds.
            state: Current pantograph state vector.
            measured_force (float | None): Most recent measured contact force in Newtons.
                Used for integral bias correction if provided.

        Returns:
            float: The optimal force command in Newtons to apply for the current control period.
        """
        if not self._scheduler.due(t):
            return self._held
        started = time.perf_counter()

        if measured_force is not None and np.isfinite(measured_force):
            error = self.setpoint - float(measured_force)
            filtered = (
                (1.0 - self.force_bias_alpha) * self.force_bias_correction
                + self.force_bias_alpha * error
            )
            self.force_bias_correction = float(np.clip(
                filtered,
                -self.force_bias_limit,
                self.force_bias_limit,
            ))
        rollout_setpoint = self.setpoint + self.force_bias_correction

        applied = self.actuator.preview_profiles(
            self.candidates, self.pred.H, self.rollout_steps
        )
        states = np.repeat(
            np.asarray(state, dtype=np.float32)[None, :],
            len(self.candidates),
            axis=0,
        )
        tracking_cost = np.zeros(len(self.candidates), dtype=np.float64)
        wave_cost = np.zeros(len(self.candidates), dtype=np.float64)
        fa = self.dist.aero_force(self.speed_ms, self.beyond)
        if self.wire_estimate is not None:
            count = len(self.candidates)
            modal_q = np.repeat(
                self.wire_estimate.displacement[None, :], count, axis=0
            )
            modal_v = np.repeat(
                self.wire_estimate.velocity[None, :], count, axis=0
            )
            modal_a = np.repeat(
                self.wire_estimate.acceleration[None, :], count, axis=0
            )
            wire_position = self.wire_estimate.position
            ripple = np.full(count, self.wire_estimate.contact_displacement())
            ripple_velocity = np.full(count, self.wire_estimate.contact_velocity())
            ripple_acceleration = np.full(count, self.wire_estimate.contact_acceleration())
        for step in range(self.rollout_steps):
            future_t = t + step * self.pred.H
            wire = _wire_features(self.dist, future_t, self.speed_ms, self.beyond)
            if self.wire_estimate is not None:
                wire = (
                    wire[0] + ripple,
                    wire[1] + ripple_velocity,
                    wire[2] + ripple_acceleration,
                )
            states, predicted_force = self.pred.predict_state_candidates(
                states, applied[step], fa, wire
            )
            if self.wire_estimate is not None:
                # The current PINN checkpoint models spring contact. Add the
                # published distributed-model contact damping around its predicted
                # state until the coupled checkpoint is retrained.
                predicted_wire_velocity = wire[1] + wire[2] * self.pred.H
                predicted_force = np.maximum(
                    predicted_force
                    + self.wire_estimate.model.params.contact_damping
                    * (states[:, 1] - predicted_wire_velocity),
                    0.0,
                )
                (
                    modal_q,
                    modal_v,
                    modal_a,
                    wire_position,
                    ripple,
                    ripple_velocity,
                    ripple_acceleration,
                ) = self.wire_estimate.preview_candidates(
                    modal_q,
                    modal_v,
                    modal_a,
                    predicted_force,
                    wire_position,
                    self.speed_ms,
                    self.pred.H,
                )
                wave_cost += (
                    self.w_wave_position * (1e3 * ripple) ** 2
                    + self.w_wave_velocity * (1e3 * ripple_velocity) ** 2
                )
            # Later samples matter more: early samples are mostly fixed by delay.
            weight = 0.5 + (step + 1) / self.rollout_steps
            tracking_cost += weight * (predicted_force - rollout_setpoint) ** 2

        cost = (
            tracking_cost
            + wave_cost
            + self.w_effort * self.candidates ** 2
            + self.w_rate * (self.candidates - self._last_command) ** 2
        )
        best_index = minimum_effort_near_optimum(
            cost,
            self.candidates,
            self.cost_tie_tolerance,
            self._last_command,
        )
        # A small offset-free command trim closes the steady-state gap between the
        # reduced PINN rollout and the coupled plant. It uses only the filtered
        # estimated-force error and remains inside the identified command authority.
        best = float(np.clip(
            self.candidates[best_index]
            + self.force_bias_command_gain * self.force_bias_correction,
            -self.command_limit,
            self.command_limit,
        ))
        self.last_latency_ms = 1e3 * (time.perf_counter() - started)
        self._latencies.append(self.last_latency_ms)
        self._deadline_misses.append(
            self.last_latency_ms > 1e3 * self.control_period
        )
        self._last_command = best
        self._held = best
        return best

    def timing_metrics(self) -> dict:
        """Calculates latency and deadline miss statistics for the controller execution.

        Returns:
            dict: A dictionary containing 'latency_p95_ms', 'latency_p99_ms',
                'deadline_miss_pct', and 'samples'.
        """
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
        """Clears the accumulated latency and deadline miss history."""
        self._latencies.clear()
        self._deadline_misses.clear()
