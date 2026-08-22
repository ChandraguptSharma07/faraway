"""Training-data generator for the PINN predictor.

Strategy: build a bank of realistic pantograph states by running the classical
solver across the operating envelope (validated + beyond-envelope speeds/tension/
turbulence). For each training sample, take a realistic state, apply a random
candidate frame force f_control, and roll the TRUE EN 50318 EOM forward by one
horizon H to get the target state. This teaches the network the local input->output
map the controller will query, over the distribution of states it will actually see.
"""

from __future__ import annotations

import numpy as np

from backend.sim.disturbance import Disturbance
from backend.sim.parameters import (
    BeyondEnvelope,
    CatenaryParams,
    PantographParams,
    kmh_to_ms,
)
from backend.sim.solver import deriv, simulate

# Operating envelope sampled for the state bank: (speed_kmh, tension_factor, turb_gain).
ENVELOPE = [
    (250, 1.0, 1.0),
    (300, 1.0, 1.0),
    (320, 0.9, 1.3),
    (340, 0.7, 2.0),
    (350, 0.6, 2.5),
    (360, 0.5, 3.0),
]
F_CONTROL_MAX = 100.0  # N  covers the 98.2 N selected cylinder-force cap


def _wire_features(dist: Disturbance, t: float, speed_ms: float, beyond: BeyondEnvelope):
    d = 1.0e-4
    y0 = float(dist.y_wire(t, speed_ms, beyond))
    yp = float(dist.y_wire(t + d, speed_ms, beyond))
    ym = float(dist.y_wire(t - d, speed_ms, beyond))
    y0d = (yp - ym) / (2 * d)
    y0dd = (yp - 2 * y0 + ym) / (d * d)
    return y0, y0d, y0dd


def _rollout_h(state, t, speed_ms, dist, panto, beyond, f_control, H, n_sub=10):
    """Integrate the true EOM from t over horizon H with constant f_control (RK4)."""
    dt = H / n_sub
    s = np.asarray(state, dtype=float)
    ti = t
    for _ in range(n_sub):
        k1, _ = deriv(s, ti, speed_ms, dist, panto, beyond, f_control)
        k2, _ = deriv(s + 0.5 * dt * k1, ti + 0.5 * dt, speed_ms, dist, panto, beyond, f_control)
        k3, _ = deriv(s + 0.5 * dt * k2, ti + 0.5 * dt, speed_ms, dist, panto, beyond, f_control)
        k4, _ = deriv(s + dt * k3, ti + dt, speed_ms, dist, panto, beyond, f_control)
        s = s + (dt / 6.0) * (k1 + 2 * k2 + 2 * k3 + k4)
        ti += dt
    return s


def generate_dataset(
    n_samples: int = 60000,
    horizon: float = 5.0e-3,
    seed: int = 7,
    panto: PantographParams | None = None,
):
    """Return (ctx[N,9], target_state[N,4]) as float32 numpy arrays.

    ctx     = [z1, z1d, z2, z2d, f_aero, f_frame, y0, y0d, y0dd]
    target  = [z1(H), z2(H), z1d(H), z2d(H)]
    """
    panto = panto or PantographParams()
    rng = np.random.default_rng(seed)

    # --- build the state bank ---
    bank = []  # (state, t, speed_ms, beyond, dist)
    per_cfg = max(1, n_samples // (len(ENVELOPE) * 4))
    for (kmh, tf, tg) in ENVELOPE:
        beyond = BeyondEnvelope(tension_factor=tf, turbulence_gain=tg)
        cat = CatenaryParams()
        dist = Disturbance(cat, seed=int(rng.integers(1, 1_000_000)))
        speed_ms = kmh_to_ms(kmh)
        res = simulate(speed_ms, duration=5.0, cat=cat, panto=panto, beyond=beyond, dist=dist)
        # sample times from the steady portion
        idx = np.where(res.t > 0.4)[0]
        pick = rng.choice(idx, size=min(per_cfg * 4, idx.size), replace=False)
        for i in pick:
            bank.append((i, res, speed_ms, beyond, dist))

    rng.shuffle(bank)
    bank = bank[:n_samples]

    ctx = np.empty((len(bank), 9), dtype=np.float64)
    tgt = np.empty((len(bank), 4), dtype=np.float64)

    # velocities aren't stored by simulate(); reconstruct via central difference on z.
    for j, (i, res, speed_ms, beyond, dist) in enumerate(bank):
        t = res.t[i]
        dt = res.t[1] - res.t[0]
        i0 = min(max(i, 1), len(res.t) - 2)
        z1d = (res.z1[i0 + 1] - res.z1[i0 - 1]) / (2 * dt)
        z2d = (res.z2[i0 + 1] - res.z2[i0 - 1]) / (2 * dt)
        state = np.array([res.z1[i], z1d, res.z2[i], z2d])

        f_control = float(rng.uniform(-F_CONTROL_MAX, F_CONTROL_MAX))
        fa = dist.aero_force(speed_ms, beyond)
        y0, y0d, y0dd = _wire_features(dist, t, speed_ms, beyond)

        sH = _rollout_h(state, t, speed_ms, dist, panto, beyond, f_control, horizon)

        ctx[j] = [state[0], state[1], state[2], state[3], fa, f_control, y0, y0d, y0dd]
        tgt[j] = [sH[0], sH[2], sH[1], sH[3]]  # z1H, z2H, z1dH, z2dH

    return ctx.astype(np.float32), tgt.astype(np.float32)
