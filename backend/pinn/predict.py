"""Load the trained PINN and use it as a fast contact-force predictor.

Provides:
  - PINNPredictor.predict_force_candidates(): one batched forward pass scoring many
    candidate control forces (what the controller calls each step).
  - PINNPredictor.predict_next_state(): one-horizon state advance (for chained rollout).
  - PINNPredictor.benchmark_latency(): the headline inference-latency number.
  - rollout_overlay(): chained PINN force trajectory vs the classical solver, for the
    credibility overlay + RMSE headline.
"""

from __future__ import annotations

import time
from pathlib import Path

import numpy as np
import torch

from backend.pinn.data import _wire_features
from backend.pinn.model import PantoPINN, PinnConfig
from backend.sim.disturbance import Disturbance
from backend.sim.parameters import (
    BeyondEnvelope,
    CatenaryParams,
    PantographParams,
    kmh_to_ms,
)
from backend.sim.solver import simulate

MODEL_PATH = Path(__file__).with_name("pinn_model.pt")


def load_model(path: Path = MODEL_PATH) -> PantoPINN:
    ckpt = torch.load(path, weights_only=False)
    cfg = PinnConfig(**ckpt["cfg"])
    model = PantoPINN(cfg)
    model.load_state_dict(ckpt["state_dict"])
    model.eval()
    return model


class PINNPredictor:
    def __init__(self, model: PantoPINN | None = None, panto: PantographParams | None = None):
        self.model = model or load_model()
        self.panto = panto or PantographParams()
        self.H = self.model.cfg.horizon
        # Crucial for constrained PaaS (Render free tier): limit PyTorch to 1 thread 
        # to avoid severe CPU thrashing on shared virtual cores.
        torch.set_num_threads(1)

    @torch.no_grad()
    def predict_force_candidates(
        self, state4, f_controls, fa: float, wirefeat
    ) -> np.ndarray:
        """Predicted contact force at tau=H for each candidate control force.

        state4 = (z1,z1d,z2,z2d); f_controls = 1D array; wirefeat = (y0,y0d,y0dd).
        Single batched forward pass.
        """
        f_controls = np.atleast_1d(np.asarray(f_controls, dtype=np.float32))
        b = len(f_controls)
        y0, y0d, y0dd = wirefeat
        ctx = np.empty((b, 8), dtype=np.float32)
        ctx[:, 0] = state4[0]; ctx[:, 1] = state4[1]
        ctx[:, 2] = state4[2]; ctx[:, 3] = state4[3]
        ctx[:, 4] = f_controls + fa
        ctx[:, 5] = y0; ctx[:, 6] = y0d; ctx[:, 7] = y0dd
        tau = torch.full((b, 1), self.H)
        f = self.model.contact_force(tau, torch.from_numpy(ctx))
        return f.squeeze(-1).numpy()

    def predict_next_state(self, state4, f_control: float, fa: float, wirefeat):
        """Advance one horizon H; returns (z1,z1d,z2,z2d) via autograd velocities."""
        y0, y0d, y0dd = wirefeat
        ctx = torch.tensor(
            [[state4[0], state4[1], state4[2], state4[3], f_control + fa, y0, y0d, y0dd]],
            dtype=torch.float32,
        )
        tau = torch.full((1, 1), self.H, requires_grad=True)
        z1, z2 = self.model.trajectory(tau, ctx)
        z1d = torch.autograd.grad(z1, tau, torch.ones_like(z1), create_graph=False, retain_graph=True)[0]
        z2d = torch.autograd.grad(z2, tau, torch.ones_like(z2))[0]
        return (
            float(z1.detach()), float(z1d.detach()),
            float(z2.detach()), float(z2d.detach()),
        )

    @torch.no_grad()
    def benchmark_latency(self, n_candidates: int = 32, iters: int = 500) -> dict:
        """Wall-clock inference latency (the headline number)."""
        state4 = (0.05, 0.0, 0.04, 0.0)
        fcs = np.linspace(-80, 80, n_candidates).astype(np.float32)
        wf = (0.01, 0.1, 1.0)
        # warmup
        for _ in range(20):
            self.predict_force_candidates(state4, fcs, 8.0, wf)
        t0 = time.perf_counter()
        for _ in range(iters):
            self.predict_force_candidates(state4, fcs, 8.0, wf)
        dt = (time.perf_counter() - t0) / iters
        # single-candidate timing
        t0 = time.perf_counter()
        for _ in range(iters):
            self.predict_force_candidates(state4, fcs[:1], 8.0, wf)
        dt1 = (time.perf_counter() - t0) / iters
        return {
            "latency_ms_single": 1e3 * dt1,
            "latency_ms_batch": 1e3 * dt,
            "n_candidates": n_candidates,
        }


def rollout_overlay(
    predictor: PINNPredictor,
    speed_kmh: float = 300.0,
    beyond: BeyondEnvelope | None = None,
    duration: float = 2.0,
    seed: int = 999,
    sample_dt: float = 2.0e-3,
):
    """Credibility overlay: at each sampled instant the PINN predicts the contact
    force one horizon H ahead from the (true) current state; we overlay that against
    the classical solver's actual force at t+H.

    This is the PINN's job — a fast PREDICTOR — so H-ahead prediction tracking the
    ground truth is the honest accuracy claim (a free-running surrogate is a different,
    much harder claim that the stiff penalty contact makes ill-conditioned).
    """
    beyond = beyond or BeyondEnvelope()
    cat = CatenaryParams()
    dist = Disturbance(cat, seed=seed)
    speed_ms = kmh_to_ms(speed_kmh)
    panto = predictor.panto
    H = predictor.H

    res = simulate(speed_ms, duration=duration, cat=cat, panto=panto, beyond=beyond, dist=dist)
    dt = res.t[1] - res.t[0]
    stride = max(1, int(round(sample_dt / dt)))

    t_pred, f_pinn = [], []
    fa = dist.aero_force(speed_ms, beyond)
    i0 = int(round(0.3 / dt))
    for i in range(i0, len(res.t) - int(round(H / dt)) - 1, stride):
        t = res.t[i]
        z1d = (res.z1[i + 1] - res.z1[i - 1]) / (2 * dt)
        z2d = (res.z2[i + 1] - res.z2[i - 1]) / (2 * dt)
        state = (res.z1[i], z1d, res.z2[i], z2d)
        wf = _wire_features(dist, t, speed_ms, beyond)
        f = float(predictor.predict_force_candidates(state, [0.0], fa, wf)[0])
        t_pred.append(t + H)
        f_pinn.append(f)

    t_pred = np.array(t_pred)
    f_pinn = np.array(f_pinn)
    f_solver = np.interp(t_pred, res.t, res.force)  # solver actual force at t+H
    rmse = float(np.sqrt(np.mean((f_pinn - f_solver) ** 2)))
    return {
        "t": t_pred,
        "f_pinn": f_pinn,
        "f_solver": f_solver,
        "rmse_N": rmse,
        "speed_kmh": speed_kmh,
        "horizon_ms": 1e3 * H,
    }


if __name__ == "__main__":
    pred = PINNPredictor()
    print("latency:", {k: round(v, 4) if isinstance(v, float) else v
                       for k, v in pred.benchmark_latency().items()})
    for kmh in (250, 300):
        ov = rollout_overlay(pred, speed_kmh=kmh)
        print(f"rollout overlay {kmh} km/h: chained-PINN-vs-solver RMSE = {ov['rmse_N']:.2f} N")
