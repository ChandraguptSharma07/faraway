from dataclasses import fields, replace

import numpy as np

from backend.catenary.model import assemble_system, interpolation_weights, structural_modes
from backend.catenary.parameters import DistributedCatenaryParams, PARAMETER_PROVENANCE
from backend.catenary.solver import simulate_distributed
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


def test_legacy_comparison_reports_both_models_without_equating_them():
    comparison = compare_with_legacy(20.0, duration=0.05, params=small_params())
    values = tuple(comparison.__dict__.values())
    assert np.all(np.isfinite(values))
    assert comparison.legacy_mean_force != comparison.distributed_mean_force
