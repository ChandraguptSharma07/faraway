from dataclasses import fields

import numpy as np

from backend.controller.actuator import (
    ACTUATOR_BASELINE,
    ACTUATOR_PROVENANCE,
    ActuatorParams,
    ForceActuator,
)
from backend.server.engine import Engine
from backend.sim.disturbance import Disturbance
from backend.sim.parameters import BeyondEnvelope, CatenaryParams, PantographParams
from backend.sim.solver import deriv


def test_actuator_parameters_are_explicitly_sourced_or_assumed():
    assert {field.name for field in fields(ActuatorParams)} == set(ACTUATOR_PROVENANCE)
    assert all(
        value.startswith(("published", "assumed", "derived"))
        for value in ACTUATOR_PROVENANCE.values()
    )
    assert ACTUATOR_BASELINE["mounting"] == "ARTICULATED_FRAME"
    assert ACTUATOR_BASELINE["railway_qualified"] is False
    assert ActuatorParams().force_limit == 98.2


def test_control_force_acts_on_frame_not_collector_head():
    state = np.array([0.02, 0.0, 0.03, 0.0])
    dist = Disturbance(CatenaryParams())
    panto = PantographParams()
    beyond = BeyondEnvelope()
    passive, _ = deriv(state, 0.0, 70.0, dist, panto, beyond, 0.0)
    active, _ = deriv(state, 0.0, 70.0, dist, panto, beyond, 30.0)
    assert active[1] == passive[1]
    assert np.isclose(active[3] - passive[3], 30.0 / panto.m2)


def test_actuator_respects_transport_delay_rate_and_force_bounds():
    dt = 1.0e-3
    params = ActuatorParams(
        transport_delay=4.0e-3,
        force_limit=20.0,
        force_rate_limit=100.0,
    )
    actuator = ForceActuator(dt, params)
    first = [actuator.step(100.0) for _ in range(4)]
    assert first == [0.0] * 4

    history = np.array([actuator.step(100.0) for _ in range(1000)])
    assert np.max(np.abs(np.diff(np.r_[0.0, history]))) <= params.force_rate_limit * dt + 1e-12
    assert np.max(np.abs(history)) <= params.force_limit


def test_actuator_preview_cannot_apply_a_new_command_before_delay():
    actuator = ForceActuator(1.0e-3, ActuatorParams(transport_delay=5.0e-3))
    preview = actuator.preview_candidates(np.array([-90.0, 90.0]), horizon=4.0e-3)
    assert np.all(preview == actuator.force)


def test_actuator_profile_preview_matches_dynamics_without_mutating_live_state():
    params = ActuatorParams(transport_delay=4.0e-3)
    live = ForceActuator(1.0e-3, params)
    reference = ForceActuator(1.0e-3, params)
    profile = live.preview_profiles(np.array([60.0]), interval=5.0e-3, n_intervals=3)
    expected = []
    for _ in range(3):
        expected.append(np.mean([reference.step(60.0) for _ in range(5)]))
    assert np.allclose(profile[:, 0], expected)
    assert live.force == 0.0
    assert live.command == 0.0


class SlowBenchmarkPredictor:
    H = 5.0e-3

    def benchmark_latency(self, **_kwargs):
        return {"latency_ms_p99": 10.0}

    def predict_force_candidates(self, _state, candidates, _fa, _wire):
        return np.full(len(candidates), 115.0)

    def predict_state_candidates(self, states, candidates, _fa, _wire):
        return np.asarray(states), np.full(len(candidates), 115.0)


def test_engine_marks_explicit_actuator_as_in_loop_and_keeps_ideal_reference():
    engine = Engine(predictor=SlowBenchmarkPredictor())
    frame = engine.frame()
    assert frame["control_timing"]["period_ms"] == 10.0
    assert frame["operating_status"] == "NOMINAL"
    assert frame["control_fidelity"] == "SENSOR_EKF_ACTUATOR_IN_LOOP"
    assert frame["actuator"]["mode"] == "SIMULATED_IN_LOOP"
    assert frame["deployment_status"] == "SIMULATION_ONLY"
    assert frame["actuator"]["parameter_status"] == "DATASHEET_BASELINE_NOT_IDENTIFIED"
    assert frame["actuator"]["baseline"]["railway_qualified"] is False
    assert "f_command" in frame["aeropinn"]
    assert "f_actuator_estimate" in frame["aeropinn"]
    assert "idealized_reference" in frame
