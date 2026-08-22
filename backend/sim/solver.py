"""Classical solver — ground truth, training-data generator, and benchmark.

Integrates the EN 50318 two-mass pantograph EOM (positive = up):

  m1*z1'' + r1*(z1'-z2') + k1*(z1-z2)                            = -P(t) + F_aero
  m2*z2'' + r2*z2'        + k2*z2 + r1*(z2'-z1') + k1*(z2-z1)    = F0 + F_act
  P(t) = max(kc*(y_wire(t) - z1), 0)     # clamp at 0 -> loss of contact (no tension)

State vector s = [z1, z1', z2, z2'];  base z3 fixed at 0 (reduced model).

Fixed-step RK4 is the primary integrator (deterministic, real-time friendly, reused
by the streaming server). A scipy `solve_ivp` cross-check lives in validate.py.

EN 50318 "statistical maximum/minimum" are defined as mean +/- 3*sigma of the contact
force; metrics() reports them that way.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

import numpy as np

from .disturbance import Disturbance
from .parameters import BeyondEnvelope, CatenaryParams, PantographParams


def _contact_force(yw: float, z1: float, kc: float) -> float:
    # Restoring (stable) penalty contact: the head presses UP into the wire, so the
    # contact force grows with head penetration past the wire datum, p = kc*(z1 - yw),
    # and the wire reacts DOWN on the head (-p enters the head EOM). Clamp at 0: when
    # the head falls below the wire (z1 < yw) contact is lost (no tension).
    # NOTE: the brief writes p = kc*(y_wire - z1) with RHS -P; that pairing is positive
    # feedback and diverges. We use the physically-equivalent stable sign convention
    # (documented in self_notes/decisions.md).
    p = kc * (z1 - yw)
    return p if p > 0.0 else 0.0


def deriv(
    state: np.ndarray,
    t: float,
    speed_ms: float,
    dist: Disturbance,
    panto: PantographParams,
    beyond: BeyondEnvelope,
    f_control: float = 0.0,
) -> tuple[np.ndarray, float]:
    """State derivative + the contact force at this instant.

    f_control is the AeroPINN force applied to the articulated frame, matching
    pneumatic active-pantograph experiments (0 for passive).
    """
    z1, z1d, z2, z2d = state
    yw = float(dist.y_wire(t, speed_ms, beyond))
    p = _contact_force(yw, z1, panto.kc)
    fa = dist.aero_force(speed_ms, beyond)

    z1dd = (-p + fa - panto.r1 * (z1d - z2d) - panto.k1 * (z1 - z2)) / panto.m1
    z2dd = (
        panto.F0 + f_control
        - panto.r2 * z2d
        - panto.k2 * z2
        - panto.r1 * (z2d - z1d)
        - panto.k1 * (z2 - z1)
    ) / panto.m2
    return np.array([z1d, z1dd, z2d, z2dd]), p


@dataclass
class SimResult:
    t: np.ndarray
    z1: np.ndarray
    z2: np.ndarray
    force: np.ndarray
    contact_lost: np.ndarray
    speed_ms: float
    step_wall_ms: float       # mean wall-clock per integration step (ms)
    eval_mask: np.ndarray     # True over the evaluated middle span window
    s_wire_eff: float         # N/m effective catenary stiffness (for uplift metric)


def static_equilibrium(
    speed_ms: float,
    dist: Disturbance,
    panto: PantographParams,
    beyond: BeyondEnvelope,
) -> np.ndarray:
    """Solve the static state so the sim starts settled (no startup transient)."""
    fa = dist.aero_force(speed_ms, beyond)
    kc, k1, k2 = panto.kc, panto.k1, panto.k2
    # Linear static system (assume in contact, y_wire mean ~ 0):
    #   k1(z1-z2) + kc*z1 = fa                       [passive equilibrium]
    #   k2*z2 + k1(z2-z1) = F0
    A = np.array([[k1 + kc, -k1], [-k1, k1 + k2]])
    b = np.array([fa, panto.F0])
    z1, z2 = np.linalg.solve(A, b)
    return np.array([z1, 0.0, z2, 0.0])


def simulate(
    speed_ms: float,
    duration: float = 6.0,
    dt: float = 1.0e-3,
    *,
    cat: CatenaryParams | None = None,
    panto: PantographParams | None = None,
    beyond: BeyondEnvelope | None = None,
    dist: Disturbance | None = None,
    f_control_fn=None,
    seed: int = 12345,
) -> SimResult:
    """Integrate the passive (or controlled) system over `duration` seconds.

    f_control_fn(t, state, force) -> float lets the controller inject a frame force.
    """
    cat = cat or CatenaryParams()
    panto = panto or PantographParams()
    beyond = beyond or BeyondEnvelope()
    dist = dist or Disturbance(cat, seed=seed)

    n = int(round(duration / dt))
    t = np.arange(n + 1) * dt
    z1 = np.empty(n + 1)
    z2 = np.empty(n + 1)
    force = np.empty(n + 1)

    state = static_equilibrium(speed_ms, dist, panto, beyond)
    fc = 0.0
    _, p0 = deriv(state, 0.0, speed_ms, dist, panto, beyond, fc)
    z1[0], z2[0], force[0] = state[0], state[2], p0

    t_start = time.perf_counter()
    for i in range(n):
        ti = t[i]
        if f_control_fn is not None:
            fc = f_control_fn(ti, state, force[i])
        # RK4
        k1v, _ = deriv(state, ti, speed_ms, dist, panto, beyond, fc)
        k2v, _ = deriv(state + 0.5 * dt * k1v, ti + 0.5 * dt, speed_ms, dist, panto, beyond, fc)
        k3v, _ = deriv(state + 0.5 * dt * k2v, ti + 0.5 * dt, speed_ms, dist, panto, beyond, fc)
        k4v, pnext = deriv(state + dt * k3v, ti + dt, speed_ms, dist, panto, beyond, fc)
        state = state + (dt / 6.0) * (k1v + 2 * k2v + 2 * k3v + k4v)
        z1[i + 1], z2[i + 1] = state[0], state[2]
        force[i + 1] = _contact_force(
            float(dist.y_wire(t[i + 1], speed_ms, beyond)), state[0], panto.kc
        )
    step_wall_ms = 1e3 * (time.perf_counter() - t_start) / n

    contact_lost = force <= 0.0

    # Evaluate a middle span (avoid boundary / startup): the window where the
    # pantograph is traversing the configured eval_span.
    x = speed_ms * t
    span_start = cat.eval_span * cat.span_length
    span_end = (cat.eval_span + 2) * cat.span_length  # two spans for a stable statistic
    eval_mask = (x >= span_start) & (x < span_end)
    if not eval_mask.any():  # fall back to the steady second half
        eval_mask = t >= 0.5 * duration

    return SimResult(
        t, z1, z2, force, contact_lost, speed_ms, step_wall_ms, eval_mask, cat.s_wire_eff
    )


def metrics(res: SimResult) -> dict:
    """EN 50318-style contact-force statistics over the evaluated window."""
    f = res.force[res.eval_mask]
    mean = float(f.mean())
    std = float(f.std())
    loss_pct = 100.0 * float((f <= 0.0).mean())
    # Wire uplift at the support = peak contact force / effective catenary stiffness.
    uplift_mm = 1e3 * float(f.max()) / res.s_wire_eff
    return {
        "speed_kmh": res.speed_ms * 3.6,
        "mean_N": mean,
        "std_N": std,
        "stat_max_N": mean + 3.0 * std,   # EN 50318 statistical maximum
        "stat_min_N": mean - 3.0 * std,   # EN 50318 statistical minimum
        "max_uplift_mm": uplift_mm,
        "loss_of_contact_pct": loss_pct,
        "step_wall_ms": res.step_wall_ms,
    }
