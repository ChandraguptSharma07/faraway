"""Real-time simulation engine: steps PASSIVE and AeroPINN on the SAME disturbance.

The WebSocket server drives this engine, pushing one frame per tick. Both systems
share a single Disturbance instance and the same live speed / tension / turbulence /
gust inputs, so their contrast is fair. Frontend controls mutate the runtime knobs.
"""

from __future__ import annotations

from collections import deque

import numpy as np

from backend.controller.actuator import (
    ACTUATOR_BASELINE,
    ActuatorParams,
    ForceActuator,
)
from backend.controller.actuator_mpc import ActuatorAwarePINNMPC
from backend.controller.environment import CatenaryPrior
from backend.controller.mpc import PINNMPCController
from backend.controller.observer import PantographEKF
from backend.controller.sensors import (
    SENSOR_BASELINE,
    SENSOR_PROVENANCE,
    MeasurementChain,
    SensorParams,
)
from backend.pinn.data import _wire_features
from backend.pinn.predict import PINNPredictor
from backend.sim.disturbance import Disturbance
from backend.sim.parameters import (
    BeyondEnvelope,
    CatenaryParams,
    PantographParams,
    kmh_to_ms,
)
from backend.sim.solver import deriv


class RuntimeParams:
    """Mutable live knobs (BeyondEnvelope is frozen, so we mirror it here)."""

    def __init__(self):
        self.speed_kmh = 250.0
        self.tension_factor = 1.0
        self.turbulence_gain = 1.0
        self.gust = 0.0  # decays each step

    def beyond(self) -> BeyondEnvelope:
        return BeyondEnvelope(
            tension_factor=self.tension_factor,
            turbulence_gain=self.turbulence_gain,
            gust=self.gust,
        )


class Engine:
    def __init__(
        self,
        dt: float = 1.0e-3,
        window_s: float = 3.0,
        seed: int = 2024,
        predictor=None,
        sensor_params: SensorParams | None = None,
    ):
        self.dt = dt
        self.cat = CatenaryParams()
        self.panto = PantographParams()
        self.rp = RuntimeParams()
        self.dist = Disturbance(self.cat, seed=seed)
        self.control_environment = CatenaryPrior(self.cat)
        self.predictor = predictor or PINNPredictor()
        self.setpoint = 115.0

        self.t = 0.0
        speed_ms = kmh_to_ms(self.rp.speed_kmh)
        self.state_p = self._equilibrium(speed_ms)
        self.state_a = self._equilibrium(speed_ms)
        self.state_ideal = self._equilibrium(speed_ms)
        self.actuator = ForceActuator(dt, ActuatorParams())
        # Separate plant and controller-side actuator objects. Pressure sensing may
        # correct the latter; the controller cannot inspect the simulated plant.
        self.actuator_estimate = ForceActuator(dt, self.actuator.params)
        self.sensor_params = sensor_params or SensorParams()
        self.sensors = MeasurementChain(self.sensor_params, seed=seed + 101)
        self.observer = PantographEKF(
            self._equilibrium(speed_ms),
            dt,
            self.control_environment,
            self.panto,
            self.sensor_params,
        )
        startup_timing = self.predictor.benchmark_latency(
            n_candidates=21, iters=100, deadline_ms=4.0
        )
        measured_period = 1.5e-3 * startup_timing["latency_ms_p99"]
        control_period = max(4.0e-3, measured_period)
        self.ideal_controller = PINNMPCController(
            self.predictor,
            self.dist,
            speed_ms,
            self.rp.beyond(),
            setpoint=self.setpoint,
            control_period=control_period,
        )
        # This controller sees the explicit delayed actuator and a 90 ms PINN
        # rollout. Ten milliseconds gives the datasheet 40 ms / assumed 4 ms actuator a
        # tested real-time margin; timing misses remain visible and unidentified
        # hardware is still a deployment blocker.
        self.controller = ActuatorAwarePINNMPC(
            self.predictor,
            self.actuator_estimate,
            self.control_environment,
            speed_ms,
            self.rp.beyond(),
            setpoint=self.setpoint,
            n_candidates=21,
            rollout_steps=18,
            control_period=10.0e-3,
            w_rate=1.5e-3,
        )

        n = int(window_s / dt)
        self.fwin_p: deque = deque(maxlen=n)
        self.fwin_a: deque = deque(maxlen=n)
        self.fwin_ideal: deque = deque(maxlen=n)
        self.observer_error_head: deque = deque(maxlen=n)
        self.observer_error_frame: deque = deque(maxlen=n)
        self.force_p = 0.0
        self.force_a = 0.0
        self.force_ideal = 0.0
        self.f_control = 0.0
        self.f_command = 0.0
        self.f_ideal = 0.0
        self.f_actuator_estimate = 0.0
        self.latency_ms = 0.0
        self.estimator_fallback = True
        self.estimator_reason = "ESTIMATOR_STARTING"
        self.gust_decay = float(np.exp(-dt / 0.18))  # ~0.18 s gust time-constant

        # Settle the start-up transient before streaming. The collector-head mode is
        # lightly damped (decay ~1.4 s), so we warm up ~0.5 s and then clear the rolling
        # metric windows, so the baseline stats start at the true steady state.
        self.step(int(0.5 / dt))
        self.fwin_p.clear()
        self.fwin_a.clear()
        self.fwin_ideal.clear()
        self.observer_error_head.clear()
        self.observer_error_frame.clear()
        self.controller.reset_timing()
        self.ideal_controller.reset_timing()

    def _equilibrium(self, speed_ms):
        from backend.sim.solver import static_equilibrium
        return static_equilibrium(speed_ms, self.dist, self.panto, self.rp.beyond())

    # --- inputs from frontend ---
    def set_speed(self, kmh: float):
        self.rp.speed_kmh = float(np.clip(kmh, 80, 400))

    def set_tension(self, factor: float):
        self.rp.tension_factor = float(np.clip(factor, 0.3, 1.0))

    def set_turbulence(self, gain: float):
        self.rp.turbulence_gain = float(np.clip(gain, 0.5, 4.0))

    def trigger_gust(self, magnitude: float = 70.0):
        self.rp.gust = float(magnitude)

    def _rk4(self, state, speed_ms, beyond, f_control):
        dt = self.dt
        k1, _ = deriv(state, self.t, speed_ms, self.dist, self.panto, beyond, f_control)
        k2, _ = deriv(state + 0.5 * dt * k1, self.t + 0.5 * dt, speed_ms, self.dist, self.panto, beyond, f_control)
        k3, _ = deriv(state + 0.5 * dt * k2, self.t + 0.5 * dt, speed_ms, self.dist, self.panto, beyond, f_control)
        k4, _ = deriv(state + dt * k3, self.t + dt, speed_ms, self.dist, self.panto, beyond, f_control)
        return state + (dt / 6.0) * (k1 + 2 * k2 + 2 * k3 + k4)

    def step(self, n_steps: int = 1):
        speed_ms = kmh_to_ms(self.rp.speed_kmh)
        for _ in range(n_steps):
            beyond = self.rp.beyond()
            # keep controller's live view in sync
            self.controller.speed_ms = speed_ms
            self.controller.beyond = beyond
            self.ideal_controller.speed_ms = speed_ms
            self.ideal_controller.beyond = beyond

            # Truth ends here. Only sampled, noisy, quantised and delayed packets
            # cross into the observer/controller side of the boundary.
            self.sensors.sample(
                self.t,
                self.state_a,
                self.f_control,
                speed_ms,
                self.dist,
                self.panto,
                beyond,
            )
            for packet in self.sensors.deliver(self.t):
                self.observer.update(packet, speed_ms, beyond)
                self.actuator_estimate.force = float(np.clip(
                    packet.actuator_force,
                    -self.actuator_estimate.params.force_limit,
                    self.actuator_estimate.params.force_limit,
                ))

            self.f_ideal = self.ideal_controller(
                self.t, self.state_ideal, self.force_ideal
            )
            estimator_healthy, self.estimator_reason = self.observer.health(self.t)
            self.estimator_fallback = not estimator_healthy
            if estimator_healthy:
                self.f_command = self.controller(
                    self.t, self.observer.state.copy(), 0.0
                )
            else:
                # Removing active force is the fail-safe behavior of this simulation;
                # real hardware still needs a safety case and independent interlock.
                self.f_command = 0.0
            self.f_control = self.actuator.step(self.f_command)
            self.f_actuator_estimate = self.actuator_estimate.step(self.f_command)
            self.latency_ms = self.controller.last_latency_ms

            self.state_p = self._rk4(self.state_p, speed_ms, beyond, 0.0)
            self.state_a = self._rk4(self.state_a, speed_ms, beyond, self.f_control)
            self.state_ideal = self._rk4(
                self.state_ideal, speed_ms, beyond, self.f_ideal
            )
            self.observer.predict(
                self.t,
                speed_ms,
                beyond,
                self.f_actuator_estimate,
            )
            self.t += self.dt

            yw = float(self.dist.y_wire(self.t, speed_ms, beyond))
            self.force_p = max(self.panto.kc * (self.state_p[0] - yw), 0.0)
            self.force_a = max(self.panto.kc * (self.state_a[0] - yw), 0.0)
            self.force_ideal = max(
                self.panto.kc * (self.state_ideal[0] - yw), 0.0
            )
            self.fwin_p.append(self.force_p)
            self.fwin_a.append(self.force_a)
            self.fwin_ideal.append(self.force_ideal)
            self.observer_error_head.append(
                float(self.observer.state[0] - self.state_a[0])
            )
            self.observer_error_frame.append(
                float(self.observer.state[2] - self.state_a[2])
            )

            # decay gust toward 0
            if self.rp.gust != 0.0:
                self.rp.gust *= self.gust_decay
                if abs(self.rp.gust) < 0.5:
                    self.rp.gust = 0.0

    def _metrics(self, win):
        if len(win) < 2:
            return {"std": 0.0, "arc_pct": 0.0}
        a = np.fromiter(win, dtype=float)
        return {"std": float(a.std()), "arc_pct": 100.0 * float((a <= 0.0).mean())}

    def frame(self) -> dict:
        speed_ms = kmh_to_ms(self.rp.speed_kmh)
        beyond = self.rp.beyond()
        yw = float(self.dist.y_wire(self.t, speed_ms, beyond))
        mp, ma = self._metrics(self.fwin_p), self._metrics(self.fwin_a)
        mi = self._metrics(self.fwin_ideal)
        timing = self.controller.timing_metrics()
        observer = self.observer.telemetry(self.t)
        head_error = np.fromiter(self.observer_error_head, dtype=float)
        frame_error = np.fromiter(self.observer_error_frame, dtype=float)
        s_wire = self.cat.s_wire_eff
        return {
            "t": round(self.t, 4),
            "speed_kmh": round(self.rp.speed_kmh, 1),
            "tension_factor": round(self.rp.tension_factor, 3),
            "turbulence_gain": round(self.rp.turbulence_gain, 3),
            "gust_active": bool(self.rp.gust != 0.0),
            "wire_mm": round(1e3 * yw, 3),
            "setpoint_N": self.setpoint,
            "operating_status": (
                "OUTSIDE_ENVELOPE"
                if self.rp.speed_kmh > 300
                or self.rp.tension_factor < 1
                or self.rp.turbulence_gain > 1
                else "NOMINAL"
            ),
            "control_fidelity": "SENSOR_EKF_ACTUATOR_IN_LOOP",
            "deployment_status": "SIMULATION_ONLY",
            # EN 50318 model terms exposed for the world-view physics overlay
            "kc": self.panto.kc,
            "f0_N": round(self.panto.F0, 1),
            "aero_N": round(self.dist.aero_force(speed_ms, beyond), 1),
            "passive": {
                "head_mm": round(1e3 * float(self.state_p[0]), 3),
                "frame_mm": round(1e3 * float(self.state_p[2]), 3),
                "contact_force": round(self.force_p, 2),
                "contact_lost": bool(self.force_p <= 0.0),
                "uplift_mm": round(1e3 * max(self.force_p, 0.0) / s_wire, 2),
                "std": round(mp["std"], 2),
                "arc_pct": round(mp["arc_pct"], 2),
            },
            "aeropinn": {
                "head_mm": round(1e3 * float(self.state_a[0]), 3),
                "frame_mm": round(1e3 * float(self.state_a[2]), 3),
                "contact_force": round(self.force_a, 2),
                "contact_lost": bool(self.force_a <= 0.0),
                "uplift_mm": round(1e3 * max(self.force_a, 0.0) / s_wire, 2),
                "std": round(ma["std"], 2),
                "arc_pct": round(ma["arc_pct"], 2),
                "f_control": round(self.f_control, 2),
                "f_command": round(self.f_command, 2),
                "f_actuator_estimate": round(self.f_actuator_estimate, 2),
            },
            "idealized_reference": {
                "contact_force": round(self.force_ideal, 2),
                "std": round(mi["std"], 2),
                "arc_pct": round(mi["arc_pct"], 2),
                "f_control": round(self.f_ideal, 2),
            },
            "pinn_latency_ms": round(self.latency_ms, 3),
            "control_timing": {
                "period_ms": round(1e3 * self.controller.control_period, 3),
                "latency_p95_ms": round(timing["latency_p95_ms"], 3),
                "latency_p99_ms": round(timing["latency_p99_ms"], 3),
                "deadline_miss_pct": round(timing["deadline_miss_pct"], 2),
                "samples": timing["samples"],
            },
            "state_estimation": {
                **observer,
                "controller_input": "ESTIMATED_STATE",
                "fallback_active": self.estimator_fallback,
                "environment_input": "DETERMINISTIC_CATENARY_PRIOR",
                "rmse_scope": "SIMULATOR_TRUTH_VALIDATION_ONLY",
                "head_rmse_mm": round(
                    1e3 * float(np.sqrt(np.mean(head_error ** 2))), 3
                ) if len(head_error) else 0.0,
                "frame_rmse_mm": round(
                    1e3 * float(np.sqrt(np.mean(frame_error ** 2))), 3
                ) if len(frame_error) else 0.0,
            },
            "sensors": {
                "sample_rate_hz": round(1.0 / self.sensor_params.sample_period, 1),
                "latency_ms": round(1e3 * self.sensor_params.delivery_latency, 2),
                "samples": self.sensors.sample_count,
                "dropouts": self.sensors.dropout_count,
                "provenance": SENSOR_PROVENANCE,
                "baseline": SENSOR_BASELINE,
            },
            "actuator": {
                "mode": "SIMULATED_IN_LOOP",
                "response_hz": self.actuator.params.response_hz,
                "delay_ms": round(1e3 * self.actuator.params.transport_delay, 2),
                "force_limit_N": self.actuator.params.force_limit,
                "force_rate_limit_N_s": self.actuator.params.force_rate_limit,
                "provenance": "mixed published/assumed",
                "parameter_status": ACTUATOR_BASELINE["status"],
                "baseline": ACTUATOR_BASELINE,
                "tested_uncertainty": {
                    "response_hz": [3.0, 10.0],
                    "delay_ms": [2.0, 15.0],
                    "result": "NOT_ROBUST_ACROSS_FULL_RANGE",
                    "nominal_300_passed": "9/9",
                    "harsh_350_passed": "6/9",
                },
            },
        }
