"""Implicit moving-contact solver for the distributed vertical model.

The coordinates are perturbations about the prestressed wire geometry.  Contact
and droppers are unilateral: neither can carry tension/compression respectively.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Callable

import numpy as np
from scipy import linalg

from backend.sim.parameters import PantographParams

from .model import DistributedSystem, assemble_system
from .parameters import DistributedCatenaryParams


ForceFunction = Callable[[float, np.ndarray, float], float]


@dataclass
class DistributedResult:
    t: np.ndarray
    x: np.ndarray
    z1: np.ndarray
    z2: np.ndarray
    wire_at_contact: np.ndarray
    force: np.ndarray
    contact_lost: np.ndarray
    slack_droppers: np.ndarray
    contact_wire: np.ndarray
    messenger_wire: np.ndarray
    speed_ms: float
    step_wall_ms: float
    system: DistributedSystem


def _external_force(system: DistributedSystem, head_force: float) -> np.ndarray:
    force = np.zeros(system.ndof)
    force[system.z1_index] = head_force
    force[system.z2_index] = system.panto.F0
    return force


def _contact_terms(
    system: DistributedSystem,
    x: float,
    speed_ms: float,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, float, float]:
    g, nodes, weights = system.contact_vector(x)
    datum, slope = system.wire_reference(x)
    datum_velocity = slope * speed_ms
    return g, nodes, weights, datum, datum_velocity


def _static_equilibrium(system: DistributedSystem, x: float, speed_ms: float) -> np.ndarray:
    """Settle the prestressed system at the initial moving-contact location."""
    q = np.zeros(system.ndof)
    g, _, _, datum, _ = _contact_terms(system, x, speed_ms)
    kc = system.params.contact_stiffness
    base_force = _external_force(system, 0.0)
    for _ in range(12):
        k, dropper_rhs, _ = system.active_structure(q)
        q_next = linalg.solve(
            k + kc * np.outer(g, g),
            base_force + dropper_rhs + kc * datum * g,
            assume_a="sym",
        )
        if np.linalg.norm(q_next - q, ord=np.inf) < 1.0e-10:
            q = q_next
            break
        q = q_next
    return q


def simulate_distributed(
    speed_ms: float,
    duration: float = 1.0,
    dt: float = 5.0e-4,
    *,
    params: DistributedCatenaryParams | None = None,
    panto: PantographParams | None = None,
    start_x: float | None = None,
    head_force_fn: ForceFunction | None = None,
    record_stride: int = 1,
    max_active_iterations: int = 6,
) -> DistributedResult:
    """Integrate the coupled wires and pantograph with average-acceleration Newmark.

    ``head_force_fn`` represents aerodynamic/control force on the collector head.
    It is intentionally external to the catenary parameter set so its provenance can
    be calibrated independently.
    """
    if speed_ms <= 0.0 or duration <= 0.0 or dt <= 0.0:
        raise ValueError("speed_ms, duration, and dt must be positive")
    if record_stride < 1:
        raise ValueError("record_stride must be at least 1")
    if max_active_iterations < 1:
        raise ValueError("max_active_iterations must be at least 1")

    system = assemble_system(params, panto)
    params = system.params
    if start_x is None:
        start_x = min(2.5 * params.span_length, 0.25 * params.length)
    steps = int(round(duration / dt))
    if steps < 1:
        raise ValueError("duration must cover at least one integration step")
    simulated_duration = steps * dt
    end_x = start_x + speed_ms * simulated_duration
    if start_x < 0.0 or end_x > params.length:
        raise ValueError(
            f"moving contact [{start_x:.1f}, {end_x:.1f}] m exceeds "
            f"the {params.length:.1f} m model"
        )

    beta, gamma = 0.25, 0.5
    sample_steps = np.unique(np.r_[np.arange(0, steps + 1, record_stride), steps])
    sample_lookup = {int(step): i for i, step in enumerate(sample_steps)}
    ns = len(sample_steps)
    n = system.n_wire

    t_out = sample_steps * dt
    x_out = start_x + speed_ms * t_out
    z1_out = np.empty(ns)
    z2_out = np.empty(ns)
    wire_out = np.empty(ns)
    force_out = np.empty(ns)
    slack_out = np.empty(ns, dtype=int)
    contact_history = np.empty((ns, n))
    messenger_history = np.empty((ns, n))

    q = _static_equilibrium(system, start_x, speed_ms)
    v = np.zeros(system.ndof)
    k, dropper_rhs, slack = system.active_structure(q)
    g, _, _, datum, datum_v = _contact_terms(system, start_x, speed_ms)
    gap = float(g @ q - datum)
    gap_v = float(g @ v - datum_v)
    trial_force = params.contact_stiffness * gap + params.contact_damping * gap_v
    active_contact = gap > 0.0 and trial_force > 0.0
    p = max(trial_force, 0.0) if active_contact else 0.0
    applied = _external_force(system, 0.0) + dropper_rhs
    if active_contact:
        applied += (params.contact_stiffness * datum + params.contact_damping * datum_v) * g
        k = k + params.contact_stiffness * np.outer(g, g)
        c = system.C + params.contact_damping * np.outer(g, g)
    else:
        c = system.C
    a = linalg.solve(system.M, applied - c @ v - k @ q, assume_a="pos")

    def record(index: int, x: float, p_now: float, slack_now: int) -> None:
        _, local_nodes, local_weights = system.contact_vector(x)
        z1_out[index] = q[system.z1_index]
        z2_out[index] = q[system.z2_index]
        wire_out[index] = system.wire_reference(x)[0] + local_weights @ q[local_nodes]
        force_out[index] = p_now
        slack_out[index] = slack_now
        contact_history[index] = q[:n]
        messenger_history[index] = q[n:2*n]

    record(0, start_x, p, slack)
    started = time.perf_counter()

    for step in range(1, steps + 1):
        ti = step * dt
        xi = start_x + speed_ms * ti
        q_pred = q + dt * v + dt * dt * (0.5 - beta) * a
        v_pred = v + dt * (1.0 - gamma) * a
        q_guess = q_pred.copy()
        contact_guess = active_contact
        head_force = 0.0 if head_force_fn is None else float(head_force_fn(ti, q, p))
        f_base = _external_force(system, head_force)

        for _ in range(max_active_iterations):
            k_eff, dropper_rhs, slack = system.active_structure(q_guess)
            g, _, _, datum, datum_v = _contact_terms(system, xi, speed_ms)
            c_eff = system.C
            rhs = f_base + dropper_rhs
            if contact_guess:
                k_eff = k_eff + params.contact_stiffness * np.outer(g, g)
                c_eff = c_eff + params.contact_damping * np.outer(g, g)
                rhs = rhs + (
                    params.contact_stiffness * datum
                    + params.contact_damping * datum_v
                ) * g

            effective_mass = (
                system.M + gamma * dt * c_eff + beta * dt * dt * k_eff
            )
            a_next = linalg.solve(
                effective_mass,
                rhs - c_eff @ v_pred - k_eff @ q_pred,
                assume_a="sym",
            )
            q_next = q_pred + beta * dt * dt * a_next
            v_next = v_pred + gamma * dt * a_next
            gap = float(g @ q_next - datum)
            gap_v = float(g @ v_next - datum_v)
            trial_force = params.contact_stiffness * gap + params.contact_damping * gap_v
            # A damper cannot create force across an open gap. Once closed, contact
            # persists only while its compressive reaction remains positive.
            next_contact = gap > 0.0 and (not contact_guess or trial_force > 0.0)
            converged = next_contact == contact_guess
            q_guess = q_next
            contact_guess = next_contact
            if converged:
                break

        q, v, a = q_next, v_next, a_next
        active_contact = contact_guess
        p = max(trial_force, 0.0) if active_contact else 0.0
        if step in sample_lookup:
            record(sample_lookup[step], xi, p, slack)

    step_wall_ms = 1.0e3 * (time.perf_counter() - started) / steps
    return DistributedResult(
        t=t_out,
        x=x_out,
        z1=z1_out,
        z2=z2_out,
        wire_at_contact=wire_out,
        force=force_out,
        contact_lost=force_out <= 0.0,
        slack_droppers=slack_out,
        contact_wire=contact_history,
        messenger_wire=messenger_history,
        speed_ms=speed_ms,
        step_wall_ms=step_wall_ms,
        system=system,
    )
