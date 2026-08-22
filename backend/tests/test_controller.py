"""AeroPINN must beat the passive baseline on both headline metrics."""

import numpy as np

from backend.controller.compare import run_comparison
from backend.pinn.predict import PINNPredictor
from backend.sim.disturbance import Disturbance
from backend.sim.parameters import BeyondEnvelope, CatenaryParams, kmh_to_ms
from backend.sim.solver import metrics, simulate


class OneUlpPerturbedDisturbance(Disturbance):
    def y_turb(self, t, beyond):
        value = super().y_turb(t, beyond)
        if getattr(t, "ndim", 0) == 0:
            return float(np.nextafter(value, np.inf))
        return np.nextafter(value, np.inf)


def test_aeropinn_flattens_force_in_validated_regime():
    pred = PINNPredictor()
    out = run_comparison(300, beyond=BeyondEnvelope(), duration=4.0, predictor=pred)
    assert out["aeropinn"]["std_N"] < 0.5 * out["passive"]["std_N"]


def test_aeropinn_holds_contact_when_passive_arcs():
    pred = PINNPredictor()
    beyond = BeyondEnvelope(tension_factor=0.5, turbulence_gain=3.5)
    for seed in (997, 998, 999, 1000, 1001):
        out = run_comparison(
            350,
            beyond=beyond,
            duration=4.0,
            seed=seed,
            predictor=pred,
        )
        # Passive must arc beyond the envelope; AeroPINN must essentially hold contact.
        assert out["passive"]["loss_of_contact_pct"] > 1.0
        assert out["aeropinn"]["loss_of_contact_pct"] < 0.5
        assert out["aeropinn"]["std_N"] < out["passive"]["std_N"]


def test_closed_loop_is_stable_to_one_ulp_wire_perturbation():
    pred = PINNPredictor()
    beyond = BeyondEnvelope(tension_factor=0.5, turbulence_gain=3.5)
    baseline = run_comparison(
        350, beyond=beyond, duration=4.0, predictor=pred
    )
    perturbed = run_comparison(
        350,
        beyond=beyond,
        duration=4.0,
        predictor=pred,
        disturbance_factory=OneUlpPerturbedDisturbance,
    )
    assert baseline["aeropinn"]["loss_of_contact_pct"] < 0.5
    assert perturbed["aeropinn"]["loss_of_contact_pct"] < 0.5
    assert abs(
        baseline["aeropinn"]["std_N"] - perturbed["aeropinn"]["std_N"]
    ) < 0.1


def test_passive_contact_metrics_converge_with_timestep():
    beyond = BeyondEnvelope(tension_factor=0.5, turbulence_gain=3.5)
    cat = CatenaryParams()
    rows = []
    for dt in (1.0e-3, 5.0e-4, 2.5e-4):
        result = simulate(
            kmh_to_ms(350),
            duration=4.0,
            dt=dt,
            cat=cat,
            beyond=beyond,
            dist=Disturbance(cat, seed=999),
        )
        rows.append(metrics(result))
    assert max(row["mean_N"] for row in rows) - min(row["mean_N"] for row in rows) < 0.2
    assert max(row["std_N"] for row in rows) - min(row["std_N"] for row in rows) < 0.5
    assert (
        max(row["loss_of_contact_pct"] for row in rows)
        - min(row["loss_of_contact_pct"] for row in rows)
        < 0.5
    )


def test_pinn_latency_is_low():
    pred = PINNPredictor()
    lat = pred.benchmark_latency()
    assert lat["latency_ms_batch"] < 5.0  # low single-digit ms target on CPU
