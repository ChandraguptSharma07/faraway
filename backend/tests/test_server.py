"""Engine / streaming-frame regression tests."""

import json

import numpy as np

from backend.server.engine import Engine


def test_frame_is_json_serializable_after_gust():
    """A gust must not produce numpy types that break ws.send_json (regression)."""
    e = Engine()
    e.set_speed(300)
    e.trigger_gust(80)
    for _ in range(20):
        e.step(20)
        json.dumps(e.frame())  # would raise TypeError on numpy bool/float


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
