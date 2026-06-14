"""Engine / streaming-frame regression tests."""

import json

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
    pk_p = pk_a = 115.0
    for _ in range(40):
        e.step(20)
        fr = e.frame()
        pk_p = max(pk_p, abs(fr["passive"]["contact_force"] - 115))
        pk_a = max(pk_a, abs(fr["aeropinn"]["contact_force"] - 115))
    # passive deviates far more than AeroPINN under the gust
    assert pk_p > 40.0
    assert pk_a < pk_p
