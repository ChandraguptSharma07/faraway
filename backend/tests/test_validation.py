"""EN 50318 validation gate as a test, plus a beyond-envelope contact-loss check."""

import dataclasses as dc

from backend.sim.parameters import BeyondEnvelope, CatenaryParams, kmh_to_ms
from backend.sim.solver import metrics, simulate
from backend.sim.validate import EN50318, _in_range, validate


def test_en50318_validation_gate():
    assert validate(verbose=False), "classical solver must land in EN 50318 ranges"


def test_metrics_in_ranges_explicit():
    for speed in (250, 300):
        m = metrics(simulate(kmh_to_ms(speed), duration=6.0))
        for key, (lo, hi) in EN50318[speed].items():
            assert _in_range(m[key], lo, hi), f"{speed} km/h {key}={m[key]} not in {lo}..{hi}"


def test_zero_loss_in_validated_regime():
    for speed in (250, 300):
        m = metrics(simulate(kmh_to_ms(speed), duration=6.0))
        assert m["loss_of_contact_pct"] == 0.0


def test_beyond_envelope_causes_contact_loss():
    """Past the validated envelope (high speed + degraded tension + raised turbulence)
    the passive system must begin losing contact."""
    beyond = BeyondEnvelope(tension_factor=0.6, turbulence_gain=2.5)
    m = metrics(simulate(kmh_to_ms(340), duration=6.0, beyond=beyond))
    assert m["loss_of_contact_pct"] > 0.0, "passive must arc beyond the envelope"
