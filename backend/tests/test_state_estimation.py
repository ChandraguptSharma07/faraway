from dataclasses import fields

import numpy as np

from backend.controller.sensors import (
    SENSOR_PROVENANCE,
    MeasurementChain,
    SensorParams,
)
from backend.server.engine import Engine
from backend.sim.disturbance import Disturbance
from backend.sim.parameters import BeyondEnvelope, CatenaryParams, PantographParams
from backend.sim.solver import static_equilibrium


def test_sensor_assumptions_have_explicit_provenance_and_latency():
    assert {field.name for field in fields(SensorParams)} == set(SENSOR_PROVENANCE)
    assert all(
        value.startswith(("published", "assumed", "derived"))
        for value in SENSOR_PROVENANCE.values()
    )
    params = SensorParams(dropout_probability=0.0)
    dist = Disturbance(CatenaryParams())
    state = static_equilibrium(70.0, dist, PantographParams(), BeyondEnvelope())
    chain = MeasurementChain(params, seed=1)
    chain.sample(0.0, state, 0.0, 70.0, dist, PantographParams(), BeyondEnvelope())
    assert chain.deliver(params.delivery_latency - 1e-6) == []
    packet = chain.deliver(params.delivery_latency)[0]
    assert packet.delivered_at - packet.sampled_at == params.delivery_latency
    assert np.isclose(
        packet.frame_position / params.displacement_resolution,
        round(packet.frame_position / params.displacement_resolution),
    )


def test_live_controller_uses_estimated_state_and_observer_stays_bounded():
    engine = Engine(sensor_params=SensorParams(dropout_probability=0.0))
    assert engine.controller.dist is engine.control_environment
    assert engine.controller.dist is not engine.dist
    assert engine.ideal_controller.dist is engine.dist
    engine.step(1500)
    frame = engine.frame()
    estimate = frame["state_estimation"]
    assert estimate["controller_input"] == "ESTIMATED_STATE"
    assert estimate["environment_input"] == "DETERMINISTIC_CATENARY_PRIOR"
    assert estimate["status"] == "HEALTHY"
    assert estimate["head_rmse_mm"] < 3.0
    assert estimate["frame_rmse_mm"] < 3.0
    assert frame["control_fidelity"] == "SENSOR_EKF_ACTUATOR_IN_LOOP"


def test_stale_sensor_data_forces_passive_command():
    engine = Engine(sensor_params=SensorParams(dropout_probability=1.0))
    engine.step(100)
    frame = engine.frame()
    assert frame["state_estimation"]["fallback_active"] is True
    assert frame["aeropinn"]["f_command"] == 0.0
    assert frame["sensors"]["dropouts"] == frame["sensors"]["samples"]
