"""EN 50318 validation gate + scipy solve_ivp cross-check.

Run:  python -m backend.sim.validate

Validation targets (EN 50318:2002 Annex A reference results). "Statistical
maximum/minimum" are mean +/- 3*sigma of the contact force.
"""

from __future__ import annotations

import numpy as np
from scipy.integrate import solve_ivp

from .disturbance import Disturbance
from .parameters import (
    BeyondEnvelope,
    CatenaryParams,
    PantographParams,
    kmh_to_ms,
)
from .solver import deriv, metrics, simulate

# EN 50318 expected ranges: (low, high) per metric per speed.
EN50318 = {
    250: {
        "mean_N": (110, 120),
        "std_N": (26, 31),
        "stat_max_N": (190, 210),
        "stat_min_N": (20, 40),
        "max_uplift_mm": (48, 55),
        "loss_of_contact_pct": (0, 0),
    },
    300: {
        "mean_N": (110, 120),
        "std_N": (32, 40),
        "stat_max_N": (210, 230),
        "stat_min_N": (-5, 20),
        "max_uplift_mm": (55, 65),
        "loss_of_contact_pct": (0, 0),
    },
}

LABELS = {
    "mean_N": "Mean contact force Fm (N)",
    "std_N": "Std deviation (N)",
    "stat_max_N": "Statistical max (N)",
    "stat_min_N": "Statistical min (N)",
    "max_uplift_mm": "Max uplift at support (mm)",
    "loss_of_contact_pct": "Loss of contact (%)",
}


def _in_range(val: float, lo: float, hi: float) -> bool:
    # Small tolerance on the zero-loss target for floating point.
    if lo == hi == 0:
        return val <= 1e-9
    return lo <= val <= hi


def solve_ivp_crosscheck(speed_kmh: float, duration: float = 6.0) -> dict:
    """Independent integration with scipy solve_ivp (RK45) to confirm the RK4 result
    is not an artifact of the fixed-step scheme."""
    cat = CatenaryParams()
    panto = PantographParams()
    beyond = BeyondEnvelope()
    dist = Disturbance(cat)
    speed_ms = kmh_to_ms(speed_kmh)

    from .solver import static_equilibrium

    s0 = static_equilibrium(speed_ms, dist, panto, beyond)

    def rhs(t, s):
        ds, _ = deriv(s, t, speed_ms, dist, panto, beyond)
        return ds

    sol = solve_ivp(rhs, (0.0, duration), s0, method="RK45", max_step=1e-3, rtol=1e-6, atol=1e-8)
    t = sol.t
    z1 = sol.y[0]
    yw = np.array([dist.y_wire(ti, speed_ms, beyond) for ti in t])
    force = np.maximum(panto.kc * (z1 - yw), 0.0)
    x = speed_ms * t
    s_start = cat.eval_span * cat.span_length
    s_end = (cat.eval_span + 2) * cat.span_length
    mask = (x >= s_start) & (x < s_end)
    f = force[mask]
    return {"mean_N": float(f.mean()), "std_N": float(f.std())}


def validate(verbose: bool = True) -> bool:
    all_pass = True
    for speed in (250, 300):
        res = simulate(kmh_to_ms(speed), duration=6.0)
        m = metrics(res)
        cross = solve_ivp_crosscheck(speed)
        if verbose:
            print(f"\n=== {speed} km/h ===  (RK4 step {m['step_wall_ms']:.3f} ms)")
            print(f"  {'metric':<28}{'value':>10}{'EN 50318':>16}   result")
            for key, (lo, hi) in EN50318[speed].items():
                val = m[key]
                ok = _in_range(val, lo, hi)
                all_pass &= ok
                rng = "0" if lo == hi == 0 else f"{lo}..{hi}"
                print(f"  {LABELS[key]:<28}{val:>10.2f}{rng:>16}   {'PASS' if ok else 'FAIL'}")
            dm = abs(cross["mean_N"] - m["mean_N"])
            ds = abs(cross["std_N"] - m["std_N"])
            print(f"  solve_ivp cross-check: mean={cross['mean_N']:.2f} std={cross['std_N']:.2f}"
                  f"  (|d mean|={dm:.2f}, |d std|={ds:.2f})")
    if verbose:
        print("\n" + ("ALL METRICS WITHIN EN 50318 RANGES — VALIDATED"
                      if all_pass else "VALIDATION FAILED"))
    return all_pass


if __name__ == "__main__":
    ok = validate()
    raise SystemExit(0 if ok else 1)
