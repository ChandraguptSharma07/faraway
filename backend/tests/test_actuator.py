from dataclasses import fields

import numpy as np

from backend.controller.actuator import (
    ACTUATOR_PROVENANCE,
    ActuatorParams,
    ForceActuator,
)
from backend.server.engine import Engine


def test_actuator_parameters_are_explicitly_sourced_or_assumed():
    assert {field.name for field in fields(ActuatorParams)} == set(ACTUATOR_PROVENANCE)
    assert all(
        value.startswith(("published", "assumed"))
        for value in ACTUATOR_PROVENANCE.values()
    )


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


class SlowBenchmarkPredictor:
    H = 5.0e-3

    def benchmark_latency(self, **_kwargs):
        return {"latency_ms_p99": 10.0}

    def predict_force_candidates(self, _state, candidates, _fa, _wire):
        return np.full(len(candidates), 115.0)


def test_engine_expands_control_period_and_marks_actuator_as_shadow_only():
    engine = Engine(predictor=SlowBenchmarkPredictor())
    frame = engine.frame()
    assert frame["control_timing"]["period_ms"] == 15.0
    assert frame["operating_status"] == "NOMINAL"
    assert frame["control_fidelity"] == "IDEALIZED_ACTUATION"
    assert frame["actuator"]["mode"] == "SHADOW_ONLY"
    assert "f_command" in frame["aeropinn"]
    assert "f_actuator_estimate" in frame["aeropinn"]
