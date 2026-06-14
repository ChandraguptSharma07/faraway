"""AeroPINN must beat the passive baseline on both headline metrics."""

from backend.controller.compare import run_comparison
from backend.pinn.predict import PINNPredictor
from backend.sim.parameters import BeyondEnvelope


def test_aeropinn_flattens_force_in_validated_regime():
    pred = PINNPredictor()
    out = run_comparison(300, beyond=BeyondEnvelope(), duration=4.0, predictor=pred)
    assert out["aeropinn"]["std_N"] < 0.5 * out["passive"]["std_N"]


def test_aeropinn_holds_contact_when_passive_arcs():
    pred = PINNPredictor()
    beyond = BeyondEnvelope(tension_factor=0.5, turbulence_gain=3.5)
    out = run_comparison(350, beyond=beyond, duration=4.0, predictor=pred)
    # passive must arc beyond the envelope; AeroPINN must essentially hold contact
    assert out["passive"]["loss_of_contact_pct"] > 1.0
    assert out["aeropinn"]["loss_of_contact_pct"] < 0.5
    assert out["aeropinn"]["std_N"] < out["passive"]["std_N"]


def test_pinn_latency_is_low():
    pred = PINNPredictor()
    lat = pred.benchmark_latency()
    assert lat["latency_ms_batch"] < 5.0  # low single-digit ms target on CPU
