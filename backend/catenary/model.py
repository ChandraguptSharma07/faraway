"""Matrix assembly and moving-contact operators for a two-wire catenary."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy import linalg

from backend.sim.parameters import PantographParams

from .parameters import DistributedCatenaryParams


def _wire_matrices(n: int, dx: float, mass_per_m: float, tension: float, ei: float):
    """Lumped mass plus tensioned Euler--Bernoulli finite-difference stiffness."""
    mass = np.full(n, mass_per_m * dx)
    mass[[0, -1]] *= 0.5
    d1 = np.zeros((n - 1, n))
    for i in range(n - 1):
        d1[i, i:i + 2] = (-1.0, 1.0)
    d2 = np.zeros((n - 2, n))
    for i in range(n - 2):
        d2[i, i:i + 3] = (1.0, -2.0, 1.0)
    k = (tension / dx) * (d1.T @ d1) + (ei / dx**3) * (d2.T @ d2)
    return np.diag(mass), k


def interpolation_weights(x: float, dx: float, n_nodes: int) -> tuple[np.ndarray, np.ndarray]:
    x = float(np.clip(x, 0.0, dx * (n_nodes - 1)))
    left = min(int(x // dx), n_nodes - 2)
    r = (x - left * dx) / dx
    return np.array([left, left + 1]), np.array([1.0 - r, r])


@dataclass
class DistributedSystem:
    params: DistributedCatenaryParams
    panto: PantographParams
    M: np.ndarray
    K_structure: np.ndarray
    C: np.ndarray
    dropper_vectors: tuple[np.ndarray, ...]
    support_nodes: np.ndarray

    @property
    def n_wire(self) -> int:
        return self.params.n_nodes

    @property
    def ndof(self) -> int:
        return self.M.shape[0]

    @property
    def z1_index(self) -> int:
        return 2 * self.n_wire

    @property
    def z2_index(self) -> int:
        return 2 * self.n_wire + 1

    def wire_reference(self, x: float) -> tuple[float, float]:
        """Presag datum and spatial derivative at longitudinal position ``x``."""
        local = (x % self.params.span_length) / self.params.span_length
        y = -4.0 * self.params.maximum_presag * local * (1.0 - local)
        dydx = -4.0 * self.params.maximum_presag * (1.0 - 2.0 * local) / self.params.span_length
        return y, dydx

    def contact_vector(self, x: float) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        nodes, weights = interpolation_weights(x, self.params.dx, self.n_wire)
        g = np.zeros(self.ndof)
        g[nodes] = -weights
        g[self.z1_index] = 1.0
        return g, nodes, weights

    def active_structure(self, q: np.ndarray) -> tuple[np.ndarray, np.ndarray, int]:
        """Add tension-only droppers; return K, equilibrium correction, slack count."""
        k = self.K_structure.copy()
        rhs = np.zeros(self.ndof)
        slack = 0
        kd = self.params.dropper_stiffness
        threshold = -self.params.dropper_preload / kd
        for g in self.dropper_vectors:
            relative = float(g @ q)  # messenger minus contact displacement
            if relative > threshold:
                k += kd * np.outer(g, g)
            else:
                # At slackening, dynamic dropper force saturates at -preload.
                rhs += self.params.dropper_preload * g
                slack += 1
        return k, rhs, slack


def assemble_system(
    params: DistributedCatenaryParams | None = None,
    panto: PantographParams | None = None,
) -> DistributedSystem:
    params = params or DistributedCatenaryParams()
    panto = panto or PantographParams()
    n = params.n_nodes
    mc, kc = _wire_matrices(
        n, params.dx, params.contact_mass_per_m,
        params.contact_tension, params.contact_bending_stiffness,
    )
    mm, km = _wire_matrices(
        n, params.dx, params.messenger_mass_per_m,
        params.messenger_tension, params.messenger_bending_stiffness,
    )
    ndof = 2 * n + 2
    M = np.zeros((ndof, ndof))
    K = np.zeros((ndof, ndof))
    M[:n, :n], M[n:2*n, n:2*n] = mc, mm
    K[:n, :n], K[n:2*n, n:2*n] = kc, km
    M[2*n, 2*n], M[2*n + 1, 2*n + 1] = panto.m1, panto.m2

    support_nodes = np.arange(0, n, params.elements_per_span)
    K[support_nodes, support_nodes] += params.steady_arm_stiffness
    messenger_support = n + support_nodes
    K[messenger_support, messenger_support] += params.messenger_support_stiffness
    for idx in (0, n - 1, n, 2*n - 1):
        K[idx, idx] += params.end_anchor_stiffness

    # Pantograph elastic structure.
    z1, z2 = 2*n, 2*n + 1
    gp = np.zeros(ndof); gp[z1], gp[z2] = 1.0, -1.0
    K += panto.k1 * np.outer(gp, gp)
    K[z2, z2] += panto.k2

    dropper_vectors = []
    for span in range(params.n_spans):
        base = span * params.span_length
        for offset in params.dropper_positions:
            nodes, weights = interpolation_weights(base + offset, params.dx, n)
            g = np.zeros(ndof)
            g[nodes] = -weights
            g[n + nodes] = weights
            dropper_vectors.append(g)

    # Proportional damping fitted to the published 0.5% modal damping at 1 and 20 Hz.
    w1, w2 = 2*np.pi*1.0, 2*np.pi*20.0
    a = 2 * params.damping_ratio * w1 * w2 / (w1 + w2)
    b = 2 * params.damping_ratio / (w1 + w2)
    C = a * M + b * K
    gd = np.zeros(ndof); gd[z1], gd[z2] = 1.0, -1.0
    C += panto.r1 * np.outer(gd, gd)
    C[z2, z2] += panto.r2

    return DistributedSystem(params, panto, M, K, C, tuple(dropper_vectors), support_nodes)


def structural_modes(system: DistributedSystem, count: int = 40):
    """Return mass-normalized modes of the fully supported, active-dropper structure."""
    k, _, _ = system.active_structure(np.zeros(system.ndof))
    values, vectors = linalg.eigh(k, system.M, subset_by_index=(0, min(count, system.ndof) - 1))
    keep = values > 1e-8
    return np.sqrt(values[keep]) / (2*np.pi), vectors[:, keep]
