import importlib
import time

from backend.validation.shadow import (
    ShadowConfig,
    ShadowThresholds,
    ShadowValidationService,
    classify_operating_point,
    evaluate_gates,
    run_shadow_scenario,
)


def metrics(mean=115.0, std=30.0, loss=0.0):
    return {
        "mean_N": mean,
        "std_N": std,
        "stat_max_N": mean + 3 * std,
        "stat_min_N": mean - 3 * std,
        "max_uplift_mm": 50.0,
        "loss_of_contact_pct": loss,
    }


def test_agreement_gates_pass_with_small_model_and_numerical_differences():
    legacy = metrics()
    distributed = metrics(mean=114.0, std=29.0)
    temporal = metrics(mean=113.5, std=28.5)
    mesh = metrics(mean=113.0, std=28.0)
    gates, rows = evaluate_gates(
        legacy, distributed, temporal, mesh, 250, ShadowThresholds()
    )
    assert all(gate["pass"] for gate in gates)
    assert all(row["pass"] for row in rows)


def test_gate_failure_is_visible_instead_of_being_relabelled_validated():
    legacy = metrics()
    distributed = metrics(mean=150.0, std=60.0, loss=5.0)
    gates, _ = evaluate_gates(
        legacy, distributed, distributed, distributed, 250
    )
    assert not all(gate["pass"] for gate in gates)
    assert {gate["name"] for gate in gates if not gate["pass"]} >= {
        "Mean-force agreement",
        "Force-variation agreement",
        "Contact-loss agreement",
    }


def test_unsupported_live_knobs_are_outside_envelope():
    snapshot = {
        "scenarios": {
            "250": {"status": "AGREEMENT"},
            "300": {"status": "INVESTIGATE"},
        }
    }
    nominal = classify_operating_point(snapshot, 250.0)
    unsupported = classify_operating_point(
        snapshot, 250.0, tension_factor=0.8, turbulence_gain=2.0
    )
    assert nominal["status"] == "AGREEMENT"
    assert unsupported["status"] == "OUTSIDE_ENVELOPE"
    assert len(unsupported["reasons"]) == 2


def test_service_warms_asynchronously_and_never_affects_controller():
    def runner(speed):
        time.sleep(0.01)
        return {
            "status": "AGREEMENT",
            "speed_kmh": speed,
            "controller_affected": False,
        }

    service = ShadowValidationService(runner)
    try:
        first = service.snapshot()
        assert first["mode"] == "SHADOW_ONLY"
        assert any(
            row["status"] == "WARMING_UP" for row in first["scenarios"].values()
        )
        final = service.wait(timeout=1.0)
        assert all(
            row["status"] == "AGREEMENT" for row in final["scenarios"].values()
        )
        assert all(
            not row["controller_affected"] for row in final["scenarios"].values()
        )
    finally:
        service.close()


def test_small_end_to_end_shadow_report_is_reproducible_and_non_authoritative():
    report = run_shadow_scenario(
        250,
        config=ShadowConfig(
            duration=0.03,
            legacy_duration=0.1,
            n_spans=2,
            fine_elements_per_span=6,
            coarse_elements_per_span=4,
            fine_dt=5.0e-4,
            coarse_dt=1.0e-3,
            record_stride=2,
        ),
    )
    assert report["status"] in {"AGREEMENT", "INVESTIGATE"}
    assert report["controller_affected"] is False
    assert report["source_commit"]
    assert len(report["gates"]) == 6


def test_server_exposes_nonblocking_shadow_snapshot(monkeypatch):
    server = importlib.import_module("backend.server.app")

    class StubService:
        def snapshot(self):
            return {
                "mode": "SHADOW_ONLY",
                "scenarios": {"250": {"status": "WARMING_UP"}},
            }

    monkeypatch.setattr(server, "_shadow_service", StubService())
    assert server.shadow_validation()["mode"] == "SHADOW_ONLY"
