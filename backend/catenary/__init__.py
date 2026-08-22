"""Distributed pantograph--catenary reference-model candidate.

This package is intentionally separate from ``backend.sim``.  The existing reduced
model remains the live baseline until this model completes independent calibration
and EN 50318:2018+A1:2022 validation.
"""

from .parameters import DistributedCatenaryParams
from .solver import DistributedResult, simulate_distributed
from .realtime import RealtimeCatenary, build_realtime_model

__all__ = [
    "DistributedCatenaryParams",
    "DistributedResult",
    "simulate_distributed",
    "RealtimeCatenary",
    "build_realtime_model",
]
