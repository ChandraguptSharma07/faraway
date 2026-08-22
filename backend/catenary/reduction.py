"""Modal projection utilities for later real-time surrogate/controller use."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .model import DistributedSystem, structural_modes


@dataclass(frozen=True)
class ModalBasis:
    frequencies_hz: np.ndarray
    vectors: np.ndarray
    mass: np.ndarray
    stiffness: np.ndarray
    damping: np.ndarray


def build_modal_basis(system: DistributedSystem, count: int = 40) -> ModalBasis:
    frequencies, vectors = structural_modes(system, count=count)
    k, _, _ = system.active_structure(np.zeros(system.ndof))
    return ModalBasis(
        frequencies_hz=frequencies,
        vectors=vectors,
        mass=vectors.T @ system.M @ vectors,
        stiffness=vectors.T @ k @ vectors,
        damping=vectors.T @ system.C @ vectors,
    )


def project_state(basis: ModalBasis, system: DistributedSystem, q: np.ndarray) -> np.ndarray:
    return basis.vectors.T @ system.M @ q


def reconstruct_state(basis: ModalBasis, modal_q: np.ndarray) -> np.ndarray:
    return basis.vectors @ modal_q
