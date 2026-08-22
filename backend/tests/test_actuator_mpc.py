import numpy as np

from backend.controller.selection import minimum_effort_near_optimum
from backend.controller.robustness import (
    ACTUATOR_SWEEP,
    OPERATING_SCENARIOS,
    evaluate_promotion,
)
from backend.pinn.predict import PINNPredictor


def test_near_optimal_selection_ignores_sub_resolution_cost_flips():
    candidates = np.array([0.0, 9.82, 19.64, 29.46])
    first = np.array([250550.95, 250550.63, 250550.60, 250551.03])
    perturbed = np.array([250550.95, 250550.61, 250550.64, 250551.03])

    assert minimum_effort_near_optimum(first, candidates, 0.185, 68.74) == 1
    assert minimum_effort_near_optimum(perturbed, candidates, 0.185, 68.74) == 1


def test_batched_finite_difference_state_matches_autograd_prediction():
    predictor = PINNPredictor()
    state = np.array([0.05, 0.1, 0.04, -0.1])
    controls = np.array([-40.0, 35.0])
    states = np.repeat(state[None, :], len(controls), axis=0)
    batched, _ = predictor.predict_state_candidates(
        states, controls, 8.0, (0.01, 0.1, 1.0)
    )
    exact = np.array([
        predictor.predict_next_state(state, float(force), 8.0, (0.01, 0.1, 1.0))
        for force in controls
    ])
    assert np.allclose(batched[:, [0, 2]], exact[:, [0, 2]], atol=1e-7)
    assert np.allclose(batched[:, [1, 3]], exact[:, [1, 3]], atol=2e-3)


def test_promotion_gates_expose_timing_or_physics_failure():
    passive = {"std_N": 30.0, "loss_of_contact_pct": 3.0, "mean_N": 115.0}
    controlled = {"std_N": 10.0, "loss_of_contact_pct": 0.0, "mean_N": 112.0}
    ready = evaluate_promotion(passive, controlled, {"deadline_miss_pct": 0.5})
    assert ready["status"] == "PROMOTION_READY"

    late = evaluate_promotion(passive, controlled, {"deadline_miss_pct": 4.0})
    assert late["status"] == "INVESTIGATE"
    assert not next(g for g in late["gates"] if g["name"] == "real-time deadline")["pass"]


def test_uncertainty_matrix_covers_declared_parameter_range():
    assert len(ACTUATOR_SWEEP) == 9
    assert (3.0, 2.0) in ACTUATOR_SWEEP
    assert (10.0, 15.0) in ACTUATOR_SWEEP
    assert set(OPERATING_SCENARIOS) == {"nominal_300", "harsh_350"}
