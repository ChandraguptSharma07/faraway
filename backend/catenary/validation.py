"""Numerical checks; these are evidence tools, not certification claims."""

from __future__ import annotations

from dataclasses import dataclass, replace

import numpy as np

from backend.sim.solver import metrics as legacy_metrics
from backend.sim.solver import simulate as simulate_legacy

from .parameters import DistributedCatenaryParams
from .solver import simulate_distributed


@dataclass(frozen=True)
class ConvergenceRow:
    elements_per_span: int
    mean_force: float
    force_std: float
    loss_fraction: float


@dataclass(frozen=True)
class ModelComparison:
    """Side-by-side statistics; disagreement is diagnostic, not a pass/fail score."""

    legacy_mean_force: float
    legacy_force_std: float
    distributed_mean_force: float
    distributed_force_std: float
    distributed_loss_percent: float


def theoretical_wave_speeds(params: DistributedCatenaryParams | None = None) -> dict[str, float]:
    params = params or DistributedCatenaryParams()
    return {
        "contact_wire": float(np.sqrt(params.contact_tension / params.contact_mass_per_m)),
        "messenger_wire": float(np.sqrt(params.messenger_tension / params.messenger_mass_per_m)),
    }


def convergence_study(
    speed_ms: float,
    duration: float = 0.25,
    meshes: tuple[int, ...] = (4, 6, 8),
    *,
    n_spans: int = 3,
) -> tuple[ConvergenceRow, ...]:
    rows = []
    for elements in meshes:
        params = replace(
            DistributedCatenaryParams(),
            n_spans=n_spans,
            elements_per_span=elements,
        )
        result = simulate_distributed(
            speed_ms,
            duration,
            dt=min(5.0e-4, params.dx / theoretical_wave_speeds(params)["contact_wire"] / 15),
            params=params,
            start_x=0.75 * params.span_length,
            record_stride=4,
        )
        rows.append(
            ConvergenceRow(
                elements,
                float(np.mean(result.force)),
                float(np.std(result.force)),
                float(np.mean(result.contact_lost)),
            )
        )
    return tuple(rows)


def compare_with_legacy(
    speed_ms: float,
    duration: float = 0.5,
    *,
    params: DistributedCatenaryParams | None = None,
) -> ModelComparison:
    """Expose model-form differences without treating the old calibration as truth."""
    distributed = simulate_distributed(
        speed_ms,
        duration,
        params=params,
        record_stride=4,
    )
    legacy = legacy_metrics(simulate_legacy(speed_ms, duration=duration))
    steady = distributed.t >= 0.5 * duration
    force = distributed.force[steady]
    return ModelComparison(
        legacy_mean_force=legacy["mean_N"],
        legacy_force_std=legacy["std_N"],
        distributed_mean_force=float(np.mean(force)),
        distributed_force_std=float(np.std(force)),
        distributed_loss_percent=100.0 * float(np.mean(force <= 0.0)),
    )
