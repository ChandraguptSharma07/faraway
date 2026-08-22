"""Modal projection utilities for later real-time surrogate/controller use."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .model import DistributedSystem, structural_modes


@dataclass(frozen=True)
class ModalBasis:
    """Reduced-order modal basis for the distributed catenary system.

    Attributes:
        frequencies_hz (np.ndarray): Modal frequencies in Hz.
        vectors (np.ndarray): Mass-normalized modal eigenvectors.
        mass (np.ndarray): Modal mass matrix (typically identity).
        stiffness (np.ndarray): Modal stiffness matrix.
        damping (np.ndarray): Modal damping matrix.
    """
    frequencies_hz: np.ndarray
    vectors: np.ndarray
    mass: np.ndarray
    stiffness: np.ndarray
    damping: np.ndarray


def build_modal_basis(system: DistributedSystem, count: int = 40) -> ModalBasis:
    """Construct a reduced modal basis from a distributed catenary system.

    Args:
        system (DistributedSystem): The fully assembled distributed system.
        count (int, optional): The number of structural modes to include. Defaults to 40.

    Returns:
        ModalBasis: The constructed modal basis containing projected matrices.
    """
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
    """Project a full physical displacement state into modal coordinates.

    Args:
        basis (ModalBasis): The reduced-order modal basis.
        system (DistributedSystem): The physical distributed system containing the mass matrix.
        q (np.ndarray): The physical displacement state vector.

    Returns:
        np.ndarray: The projected modal displacement vector.
    """
    return basis.vectors.T @ system.M @ q


def reconstruct_state(basis: ModalBasis, modal_q: np.ndarray) -> np.ndarray:
    """Reconstruct the full physical displacement state from modal coordinates.

    Args:
        basis (ModalBasis): The reduced-order modal basis.
        modal_q (np.ndarray): The modal displacement state vector.

    Returns:
        np.ndarray: The reconstructed physical displacement state vector.
    """
    return basis.vectors @ modal_q
