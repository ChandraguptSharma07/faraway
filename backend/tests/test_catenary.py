from dataclasses import fields, replace

import numpy as np

from backend.catenary.model import assemble_system, interpolation_weights, structural_modes
from backend.catenary.parameters import DistributedCatenaryParams, PARAMETER_PROVENANCE
from backend.catenary.solver import simulate_distributed
from backend.catenary.realtime import RealtimeCatenary, build_realtime_model
from backend.catenary.validation import compare_with_legacy, theoretical_wave_speeds


def small_params(**changes):
    return replace(
        DistributedCatenaryParams(),
        n_spans=2,
        elements_per_span=6,
        **changes,
    )


def test_every_physical_input_has_provenance():
    names = {item.name for item in fields(DistributedCatenaryParams)}
    assert names == set(PARAMETER_PROVENANCE)
    assert all(value.startswith(("published", "assumed")) for value in PARAMETER_PROVENANCE.values())


def test_assembled_system_is_symmetric_and_has_positive_mass():
    system = assemble_system(small_params())
    assert np.allclose(system.M, system.M.T)
    assert np.allclose(system.K_structure, system.K_structure.T)
    assert np.all(np.diag(system.M) > 0.0)
    assert system.ndof == 2 * system.params.n_nodes + 2


def test_moving_contact_interpolation_is_partition_of_unity():
    nodes, weights = interpolation_weights(37.2, 10.0, 13)
    assert tuple(nodes) == (3, 4)
    assert np.isclose(np.sum(weights), 1.0)
    assert np.all(weights >= 0.0)


def test_dropper_can_go_slack():
    system = assemble_system(small_params())
    q = np.zeros(system.ndof)
    g = system.dropper_vectors[0]
    q += (-2.0 * system.params.dropper_preload / system.params.dropper_stiffness) * g / (g @ g)
    _, _, slack = system.active_structure(q)
    assert slack >= 1


def test_distributed_solver_couples_pantograph_and_both_wires():
    params = small_params()
    result = simulate_distributed(
        20.0,
        duration=0.05,
        dt=5.0e-4,
        params=params,
        start_x=30.0,
        record_stride=5,
    )
    assert np.all(np.isfinite(result.force))
    assert np.max(result.force) > 0.0
    assert np.max(np.abs(result.contact_wire)) > 0.0
    assert np.max(np.abs(result.messenger_wire)) > 0.0
    assert result.contact_wire.shape[1] == params.n_nodes


def test_modes_and_wave_speed_are_physical():
    system = assemble_system(small_params())
    frequencies, modes = structural_modes(system, count=8)
    speeds = theoretical_wave_speeds(system.params)
    assert np.all(frequencies > 0.0)
    assert np.all(np.diff(frequencies) >= 0.0)
    assert modes.shape[1] == len(frequencies)
    assert 100.0 < speeds["contact_wire"] < 150.0


def test_newmark_solution_converges_when_time_step_is_halved():
    params = small_params()
    coarse = simulate_distributed(
        20.0, 0.05, 1.0e-3, params=params, start_x=30.0
    )
    fine = simulate_distributed(
        20.0, 0.05, 5.0e-4, params=params, start_x=30.0, record_stride=2
    )
    assert np.max(np.abs(coarse.force - fine.force)) < 0.1


def test_initial_head_force_is_included_in_static_equilibrium():
    params = small_params()
    head_force = 20.0
    common = {
        "speed_ms": 20.0,
        "duration": 0.01,
        "dt": 5.0e-4,
        "params": params,
        "start_x": 30.0,
        "head_force_fn": lambda _t, _q, _p: head_force,
    }
    unloaded = simulate_distributed(**common)
    loaded = simulate_distributed(**common, initial_head_force=head_force)
    assert loaded.force[0] > unloaded.force[0] + 15.0
    assert np.all(np.isfinite(loaded.force))


def test_legacy_comparison_reports_both_models_without_equating_them():
    comparison = compare_with_legacy(20.0, duration=0.05, params=small_params())
    values = tuple(comparison.__dict__.values())
    assert np.all(np.isfinite(values))
    assert comparison.legacy_mean_force != comparison.distributed_mean_force


def test_realtime_lanes_develop_force_dependent_distinct_ripples():
    model = build_realtime_model(params=replace(
        small_params(), n_spans=8, elements_per_span=6
    ), mode_count=24)
    passive = RealtimeCatenary(model, 1.0e-3)
    active = RealtimeCatenary(model, 1.0e-3)
    for _ in range(800):
        passive.step(150.0, 250.0 / 3.6)
        active.step(90.0, 250.0 / 3.6)
    assert np.all(np.isfinite(passive.displacement))
    assert np.all(np.isfinite(active.displacement))
    assert not np.allclose(passive.displacement, active.displacement)
    assert passive.contact_displacement() != active.contact_displacement()


def test_realtime_modal_preview_does_not_mutate_live_wire():
    model = build_realtime_model(params=replace(
        small_params(), n_spans=8, elements_per_span=6
    ), mode_count=24)
    wire = RealtimeCatenary(model, 1.0e-3)
    before = wire.displacement.copy()
    preview = wire.preview(150.0, 250.0 / 3.6)
    assert np.array_equal(wire.displacement, before)
    assert np.any(preview.displacement != before)


def test_36_mode_live_response_is_close_to_48_mode_reference():
    params = replace(small_params(), n_spans=8, elements_per_span=6)
    coarse = RealtimeCatenary(
        build_realtime_model(params=params, mode_count=36), 1.0e-3
    )
    reference = RealtimeCatenary(
        build_realtime_model(params=params, mode_count=48), 1.0e-3
    )
    coarse_trace, reference_trace = [], []
    for i in range(2_000):
        force = 115.0 + 20.0 * np.sin(2.0 * np.pi * 5.0 * i * 1.0e-3)
        coarse_trace.append(coarse.step(force, 250.0 / 3.6))
        reference_trace.append(reference.step(force, 250.0 / 3.6))
    difference = np.asarray(coarse_trace[500:]) - np.asarray(reference_trace[500:])
    assert 1e3 * np.sqrt(np.mean(difference ** 2)) < 0.25


def test_live_tension_change_preserves_state_and_lowers_wave_speed():
    from backend.server.engine import Engine

    engine = Engine()
    engine.step(50)
    physical_before = engine.wire_p.model.modes @ engine.wire_p.displacement
    nominal_speed = engine.catenary_model.contact_wave_speed
    engine.set_tension(0.7)
    engine._sync_catenary_tension()
    physical_after = engine.wire_p.model.modes @ engine.wire_p.displacement
    assert engine.catenary_model.contact_wave_speed < nominal_speed
    # Modal truncation makes reprojection approximate, but it must not reset motion.
    assert np.linalg.norm(physical_after) > 0.0
    assert np.linalg.norm(physical_after - physical_before) < 0.01
