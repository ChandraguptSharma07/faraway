"""Sampled sensor boundary between the simulated plant and deployable control.

The controller must not read the simulator state directly.  This module is the only
place where plant truth becomes measurements.  Published specifications establish
the scale of the noise/quantisation model; latency, bias and dropout are explicit
test-rig assumptions until measured on hardware.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass

import numpy as np

from backend.sim.disturbance import Disturbance
from backend.sim.parameters import BeyondEnvelope, PantographParams
from backend.sim.solver import deriv


@dataclass(frozen=True)
class SensorParams:
    """Parameters defining sensor performance and error characteristics.

    Attributes:
        sample_period: Time between sensor samples in seconds.
        delivery_latency: Delay from sampling to measurement availability in seconds.
        dropout_probability: Probability of a packet being lost during transmission.
        displacement_resolution: Quantisation resolution of the displacement sensor in meters.
        displacement_noise_std: Standard deviation of displacement sensor noise in meters.
        displacement_bias_std: Standard deviation of the static displacement bias in meters.
        acceleration_resolution: Quantisation resolution of the accelerometer in m/s^2.
        acceleration_noise_std: Standard deviation of the accelerometer noise in m/s^2.
        acceleration_bias_std: Standard deviation of the static accelerometer bias in m/s^2.
        force_resolution: Quantisation resolution of the force sensor in Newtons.
        force_noise_std: Standard deviation of the force sensor noise in Newtons.
        force_bias_std: Standard deviation of the static force sensor bias in Newtons.
        stale_after: Time after which a delayed packet is considered stale and discarded in seconds.
    """
    sample_period: float = 2.0e-3
    delivery_latency: float = 2.0e-3
    dropout_probability: float = 1.0e-3
    displacement_resolution: float = 0.05e-3
    displacement_noise_std: float = 0.05e-3
    displacement_bias_std: float = 0.02e-3
    acceleration_resolution: float = 0.005
    acceleration_noise_std: float = 0.010
    acceleration_bias_std: float = 0.005
    force_resolution: float = 0.10
    force_noise_std: float = 0.20
    force_bias_std: float = 0.05
    stale_after: float = 20.0e-3


SENSOR_PROVENANCE = {
    "sample_period": "assumed-500hz-control-acquisition",
    "delivery_latency": "assumed-acquisition-plus-published-1ms-pressure-response",
    "dropout_probability": "assumed-test-rig-packet-loss",
    "displacement_resolution": "assumed-conditioned-lvdt-acquisition-resolution",
    "displacement_noise_std": "assumed-conditioned-lvdt-noise",
    "displacement_bias_std": "assumed-post-zeroing-residual-lvdt-bias",
    "acceleration_resolution": "published-pcb-353b34-broadband-resolution",
    "acceleration_noise_std": "assumed-mounted-sensor-plus-acquisition-noise",
    "acceleration_bias_std": "assumed-post-calibration-mounted-sensor-bias",
    "force_resolution": "derived-smc-pse300-1-over-1000-display-resolution",
    "force_noise_std": "assumed-pressure-to-force-chain-noise",
    "force_bias_std": "assumed-post-zeroing-pressure-to-force-chain-bias",
    "stale_after": "assumed-two-control-period-safety-timeout",
}

SENSOR_BASELINE = {
    "status": "DATASHEET_BASELINE_NOT_IDENTIFIED",
    "controller_input": "ESTIMATED_STATE",
    "sample_rate_hz": 500.0,
    "latency_ms": 2.0,
    "displacement_sensor": "two TE miniature LVDT-class channels",
    "accelerometer": "PCB 353B34 class",
    "pressure_controller": "SMC PSE300 class",
    "railway_qualified": False,
}


@dataclass(frozen=True)
class SensorPacket:
    """A collection of synchronized sensor measurements sampled at a single instant.

    Attributes:
        sampled_at: The simulation time the sample was taken in seconds.
        delivered_at: The simulation time the packet will be available to the controller in seconds.
        frame_position: Absolute vertical position of the pantograph frame in meters.
        head_frame_displacement: Relative displacement between the pantograph head and frame in meters.
        head_acceleration: Vertical acceleration of the pantograph head in m/s^2.
        frame_acceleration: Vertical acceleration of the pantograph frame in m/s^2.
        actuator_force: The measured force applied by the actuator in Newtons.
    """
    sampled_at: float
    delivered_at: float
    frame_position: float
    head_frame_displacement: float
    head_acceleration: float
    frame_acceleration: float
    actuator_force: float


def _quantise(value: float, resolution: float) -> float:
    """Quantise a continuous value to discrete steps defined by the resolution.

    Args:
        value: The continuous input value.
        resolution: The discrete step size.

    Returns:
        The value rounded to the nearest multiple of the resolution.
    """
    return float(np.round(value / resolution) * resolution)


class MeasurementChain:
    """Generate delayed packets from truth without exposing truth downstream.

    Simulates the entire measurement pipeline including noise, bias, quantisation,
    dropout, and latency.
    """

    def __init__(self, params: SensorParams | None = None, seed: int = 7321):
        """Initialize the measurement chain.

        Args:
            params: Sensor configuration parameters. Defaults to standard SensorParams.
            seed: Random seed for noise and dropout generation.
        """
        self.params = params or SensorParams()
        self.rng = np.random.default_rng(seed)
        self._next_sample = 0.0
        self._pending: deque[SensorPacket] = deque()
        self.sample_count = 0
        self.dropout_count = 0
        p = self.params
        self._bias = np.array([
            self.rng.normal(0.0, p.displacement_bias_std),
            self.rng.normal(0.0, p.displacement_bias_std),
            self.rng.normal(0.0, p.acceleration_bias_std),
            self.rng.normal(0.0, p.acceleration_bias_std),
            self.rng.normal(0.0, p.force_bias_std),
        ])

    def sample(
        self,
        t: float,
        state: np.ndarray,
        actuator_force: float,
        speed_ms: float,
        dist: Disturbance,
        panto: PantographParams,
        beyond: BeyondEnvelope,
    ) -> None:
        """Sample the true plant state and generate a delayed, noisy sensor packet.

        The generated packet is placed in a pending queue until its delivery time.
        If the current time hasn't reached the next sample period, or if a packet
        is dropped (based on dropout probability), no packet is generated.

        Args:
            t: Current simulation time in seconds.
            state: True state vector of the plant.
            actuator_force: True force exerted by the actuator.
            speed_ms: Operating speed in m/s.
            dist: Current disturbance model.
            panto: Pantograph mechanical parameters.
            beyond: Envelope parameters scaling the disturbance.
        """
        if t + 1.0e-12 < self._next_sample:
            return
        self._next_sample += self.params.sample_period
        self.sample_count += 1
        if self.rng.random() < self.params.dropout_probability:
            self.dropout_count += 1
            return

        dx, _ = deriv(state, t, speed_ms, dist, panto, beyond, actuator_force)
        p = self.params
        values = np.array([
            state[2], state[0] - state[2], dx[1], dx[3], actuator_force
        ]) + self._bias
        values += self.rng.normal(
            0.0,
            [p.displacement_noise_std, p.displacement_noise_std,
             p.acceleration_noise_std,
             p.acceleration_noise_std, p.force_noise_std],
        )
        values = np.array([
            _quantise(values[0], p.displacement_resolution),
            _quantise(values[1], p.displacement_resolution),
            _quantise(values[2], p.acceleration_resolution),
            _quantise(values[3], p.acceleration_resolution),
            _quantise(values[4], p.force_resolution),
        ])
        self._pending.append(SensorPacket(
            sampled_at=float(t),
            delivered_at=float(t + p.delivery_latency),
            frame_position=float(values[0]),
            head_frame_displacement=float(values[1]),
            head_acceleration=float(values[2]),
            frame_acceleration=float(values[3]),
            actuator_force=float(values[4]),
        ))

    def deliver(self, t: float) -> list[SensorPacket]:
        """Retrieve all sensor packets that have arrived by the current time.

        Args:
            t: Current simulation time in seconds.

        Returns:
            A list of SensorPacket objects whose delivery time is less than or equal to `t`.
        """
        packets = []
        while self._pending and self._pending[0].delivered_at <= t + 1.0e-12:
            packets.append(self._pending.popleft())
        return packets
