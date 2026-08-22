"""Engine / streaming-frame regression tests."""

import json

import numpy as np

from backend.server.engine import Engine
from backend.server.app import physical_calibration_status
from backend.sim.parameters import kmh_to_ms


def test_lanes_share_forcing_but_keep_independent_wire_states():
    e = Engine(seed=1729)
    speed_ms = kmh_to_ms(e.rp.speed_kmh)
    beyond = e.rp.beyond()

    assert e.env_p.base is e.env_a.base
    assert e.env_p.wire is not e.env_a.wire
    for t in np.linspace(0.0, 1.0, 11):
        assert e.env_p.base.y_wire(t, speed_ms, beyond) == e.env_a.base.y_wire(
            t, speed_ms, beyond
        )

    for _ in range(250):
        e.wire_p.step(150.0, speed_ms)
        e.wire_a.step(90.0, speed_ms)
    assert not np.allclose(e.wire_p.displacement, e.wire_a.displacement)
    assert e.wire_p.contact_displacement() != e.wire_a.contact_displacement()


def test_frame_is_json_serializable_after_gust():
    """A gust must not produce numpy types that break ws.send_json (regression)."""
    e = Engine()
    e.set_speed(300)
    e.trigger_gust(80)
    for _ in range(20):
        e.step(20)
        json.dumps(e.frame())  # would raise TypeError on numpy bool/float


def test_physical_calibration_status_blocks_unsupported_claims():
    status = physical_calibration_status()
    assert status["status"] == "REFERENCE_BENCHMARK_ONLY"
    assert status["route_identified"] is False
    assert status["hardware_validated"] is False
    assert status["asset_boundary"]["lastochka_glb"] == "visual geometry only"
    assert status["required_dataset_groups"]


def test_gust_passive_spikes_aeropinn_absorbs():
    e = Engine()
    e.set_speed(250)
    for _ in range(30):
        e.step(20)
    e.trigger_gust(80)
    passive_error, active_error = [], []
    for _ in range(800):
        e.step()
        passive_error.append(e.force_p - 115.0)
        active_error.append(e.force_a - 115.0)
    # A causal controller cannot anticipate the first gust peak. After one published
    # 40 ms actuator-response interval, it must reduce disturbance energy.
    passive_post = np.asarray(passive_error[40:])
    active_post = np.asarray(active_error[40:])
    assert np.max(np.abs(passive_error)) > 40.0
    assert np.sqrt(np.mean(active_post ** 2)) < np.sqrt(np.mean(passive_post ** 2))
