"""Deterministic candidate selection for numerically near-equivalent MPC costs."""

from __future__ import annotations

import numpy as np


def minimum_effort_near_optimum(
    costs: np.ndarray,
    candidates: np.ndarray,
    tolerance: float,
    previous: float = 0.0,
) -> int:
    """Select the least forceful candidate inside a resolved cost band.

    Costs closer than ``tolerance`` cannot be distinguished by the declared sensor
    resolution. Choosing minimum effort prevents roundoff from flipping adjacent
    commands; the previous command breaks equal-effort ties.
    """
    values = np.asarray(costs, dtype=np.float64)
    commands = np.asarray(candidates, dtype=np.float64)
    if values.ndim != 1 or commands.shape != values.shape:
        raise ValueError("costs and candidates must be matching one-dimensional arrays")
    if tolerance < 0.0:
        raise ValueError("cost tolerance must be non-negative")
    if not np.all(np.isfinite(values)):
        raise ValueError("candidate costs must be finite")

    near = np.flatnonzero(values <= float(np.min(values)) + tolerance)
    order = np.lexsort((
        near,
        np.abs(commands[near] - previous),
        np.abs(commands[near]),
    ))
    return int(near[order[0]])
