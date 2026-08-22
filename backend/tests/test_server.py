"""Engine / streaming-frame regression tests."""

import json

import numpy as np

import backend.server.app as app_module
from backend.server.engine import Engine
from backend.server.app import physical_calibration_status
from backend.server.journeys import JourneyStore
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
        json.dumps(e.audit_sample())


def test_engine_emits_one_native_rate_audit_sample_per_step():
    e = Engine()
    samples = []
    e.step(3, audit_callback=samples.append)
    assert len(samples) == 3
    assert np.isclose(samples[-1]["t_s"], e.t)
    assert "contact_force_N" in samples[-1]["passive"]
    assert samples[-1]["timing"]["control_authority_N"] == 25.0


def test_engine_exposes_reproducibility_constants_snapshot():
    engine = Engine()
    snapshot = engine.constants_snapshot()

    assert snapshot["pantograph"]["m1"] == engine.panto.m1
    assert snapshot["distributed_catenary"]["contact_tension"] == 20_000.0
    assert snapshot["actuator"]["response_time"] == 40.0e-3
    assert snapshot["controller"]["setpoint_N"] == 115.0
    assert snapshot["solver"]["integration_step_s"] == engine.dt


def test_records_endpoint_pages_persistent_events(tmp_path, monkeypatch):
    store = JourneyStore(tmp_path)
    journey = store.create()
    journey.event("ACCESSIBILITY_REVIEW", {"result": "ready"})
    journey.finalize()
    monkeypatch.setattr(app_module, "_journey_store", store)

    payload = app_module.get_journey_records(
        journey.id,
        source="events",
        limit=1,
    )
    assert payload["records"][0]["event_type"] == "ACCESSIBILITY_REVIEW"
    assert payload["snapshot_bytes"] > 0
    assert any(
        route.path == "/api/journeys/{journey_id}/records"
        for route in app_module.app.routes
    )


def test_controller_fails_safe_outside_pinn_training_support():
    engine = Engine()
    engine.set_tension(0.4)
    engine.set_turbulence(4.0)
    engine.step(100)

    assert engine.f_command == 0.0
    assert engine.controller_enabled is False
    assert engine.controller_reason == "OUTSIDE_PINN_TRAINING_SUPPORT"
    assert engine.frame()["control_timing"]["controller_enabled"] is False


def test_direct_catenary_coupling_converges_within_force_tolerance():
    engine = Engine(seed=999)
    engine.set_speed(350.0)
    engine.set_tension(0.5)
    engine.set_turbulence(3.5)
    maximum_residual = 0.0
    for _ in range(300):
        engine.step()
        maximum_residual = max(
            maximum_residual,
            engine.wire_p.last_coupling_residual,
            engine.wire_a.last_coupling_residual,
        )
    assert maximum_residual < 0.05


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
