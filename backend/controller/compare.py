"""Run PASSIVE vs AeroPINN on the SAME disturbance and compare headline metrics.

Headline metrics: contact-force standard deviation and % time in contact loss
(arcing), passive vs AeroPINN.

Run:  python -m backend.controller.compare
"""

from __future__ import annotations

import numpy as np

from backend.controller.mpc import PINNMPCController
from backend.pinn.predict import PINNPredictor
from backend.sim.disturbance import Disturbance
from backend.sim.parameters import BeyondEnvelope, CatenaryParams, PantographParams, kmh_to_ms
from backend.sim.solver import metrics, simulate


def run_comparison(
    speed_kmh: float,
    beyond: BeyondEnvelope | None = None,
    duration: float = 6.0,
    seed: int = 999,
    predictor: PINNPredictor | None = None,
):
    beyond = beyond or BeyondEnvelope()
    predictor = predictor or PINNPredictor()
    cat = CatenaryParams()
    panto = PantographParams()
    speed_ms = kmh_to_ms(speed_kmh)

    # identical disturbance for both systems
    dist_p = Disturbance(cat, seed=seed)
    dist_a = Disturbance(cat, seed=seed)

    passive = simulate(speed_ms, duration=duration, cat=cat, panto=panto, beyond=beyond, dist=dist_p)

    controller = PINNMPCController(predictor, dist_a, speed_ms, beyond)
    aeropinn = simulate(
        speed_ms, duration=duration, cat=cat, panto=panto, beyond=beyond, dist=dist_a,
        f_control_fn=controller,
    )

    mp, ma = metrics(passive), metrics(aeropinn)
    return {
        "speed_kmh": speed_kmh,
        "passive": mp,
        "aeropinn": ma,
        "passive_res": passive,
        "aeropinn_res": aeropinn,
    }


def _fmt(m):
    return f"mean={m['mean_N']:6.1f}  std={m['std_N']:6.2f}  loss={m['loss_of_contact_pct']:5.2f}%"


if __name__ == "__main__":
    pred = PINNPredictor()
    print("PINN latency:", {k: round(v, 4) if isinstance(v, float) else v
                            for k, v in pred.benchmark_latency().items()})
    scenarios = [
        ("validated 300 (no arcing)", 300, BeyondEnvelope()),
        ("beyond 340 (passive arcs)", 340, BeyondEnvelope(tension_factor=0.5, turbulence_gain=4.0)),
        ("beyond 350 (passive arcs)", 350, BeyondEnvelope(tension_factor=0.5, turbulence_gain=3.5)),
        ("beyond 360 (extreme)", 360, BeyondEnvelope(tension_factor=0.4, turbulence_gain=4.0)),
    ]
    for name, kmh, b in scenarios:
        out = run_comparison(kmh, beyond=b, predictor=pred)
        print(f"\n[{name}]")
        print("  PASSIVE :", _fmt(out["passive"]))
        print("  AeroPINN:", _fmt(out["aeropinn"]))
        dstd = 100 * (1 - out["aeropinn"]["std_N"] / out["passive"]["std_N"])
        print(f"  -> std reduced {dstd:.0f}%, "
              f"arc {out['passive']['loss_of_contact_pct']:.2f}% -> "
              f"{out['aeropinn']['loss_of_contact_pct']:.2f}%")
