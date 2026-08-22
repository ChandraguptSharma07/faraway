"""Train the PINN predictor: L = w_data * L_data + w_ode * L_ode.

  L_data : supervised agreement with the classical solver at tau = H (positions and
           velocities; velocities via autograd of the trajectory).
  L_ode  : EN 50318 EOM residual at random collocation points in (0, H), with the
           network's second time-derivatives fed back through the equations of motion.

Run:  python -m backend.pinn.train
Saves: backend/pinn/pinn_model.pt
"""

from __future__ import annotations

import time
from pathlib import Path

import numpy as np
import torch

from backend.pinn.data import generate_dataset
from backend.pinn.model import SCALE, PantoPINN, PinnConfig

MODEL_PATH = Path(__file__).with_name("pinn_model.pt")


def train(
    n_samples: int = 60000,
    epochs: int = 350,
    batch: int = 4096,
    lr: float = 2.0e-3,
    w_ode: float = 0.05,
    seed: int = 0,
    verbose: bool = True,
) -> dict:
    """Trains the Physics-Informed Neural Network (PINN) predictor.

    The loss function combines a data-driven loss (supervised agreement with a classical
    solver at tau = H) and an ODE residual loss (EN 50318 equation of motion residual at
    random collocation points).

    Args:
        n_samples (int, optional): Number of dataset samples to generate. Defaults to 60000.
        epochs (int, optional): Number of training epochs. Defaults to 350.
        batch (int, optional): Batch size for training. Defaults to 4096.
        lr (float, optional): Learning rate for the Adam optimizer. Defaults to 2.0e-3.
        w_ode (float, optional): Weight for the ODE loss term. Defaults to 0.05.
        seed (int, optional): Random seed for reproducibility. Defaults to 0.
        verbose (bool, optional): Whether to print training progress. Defaults to True.

    Returns:
        dict: A dictionary containing the validation force RMSE ('val_force_rmse_N') and
            the path to the saved model ('path').
    """
    torch.manual_seed(seed)
    cfg = PinnConfig()
    H = cfg.horizon

    if verbose:
        print("generating dataset...")
    t0 = time.perf_counter()
    ctx_np, tgt_np = generate_dataset(n_samples=n_samples, horizon=H)
    if verbose:
        print(f"  {len(ctx_np)} samples in {time.perf_counter() - t0:.1f}s")

    ctx = torch.from_numpy(ctx_np)
    tgt = torch.from_numpy(tgt_np)

    # train / val split
    n = len(ctx)
    perm = torch.randperm(n)
    n_val = n // 10
    val_idx, tr_idx = perm[:n_val], perm[n_val:]
    ctx_tr, tgt_tr = ctx[tr_idx], tgt[tr_idx]
    ctx_val, tgt_val = ctx[val_idx], tgt[val_idx]

    model = PantoPINN(cfg)
    opt = torch.optim.Adam(model.parameters(), lr=lr)
    sched = torch.optim.lr_scheduler.CosineAnnealingLR(opt, T_max=epochs)

    sz, szd = SCALE["z"], SCALE["zd"]
    f_sc = 50.0  # N residual scale

    def data_loss(c, y):
        """Computes the data-driven loss component.

        Args:
            c (torch.Tensor): Context tensor containing initial states and inputs.
            y (torch.Tensor): Target tensor containing the true states at tau = H.

        Returns:
            torch.Tensor: The mean squared error loss for positions and velocities.
        """
        tau = torch.full((c.shape[0], 1), H, requires_grad=True)
        z1, z2 = model.trajectory(tau, c)
        z1d = torch.autograd.grad(z1, tau, torch.ones_like(z1), create_graph=True)[0]
        z2d = torch.autograd.grad(z2, tau, torch.ones_like(z2), create_graph=True)[0]
        l_pos = ((z1 - y[:, 0:1]) / sz) ** 2 + ((z2 - y[:, 1:2]) / sz) ** 2
        l_vel = ((z1d - y[:, 2:3]) / szd) ** 2 + ((z2d - y[:, 3:4]) / szd) ** 2
        return (l_pos + l_vel).mean()

    def ode_loss(c):
        """Computes the Ordinary Differential Equation (ODE) residual loss.

        Evaluates the network at random collocation points in (0, H) and penalizes
        deviations from the physical equations of motion.

        Args:
            c (torch.Tensor): Context tensor containing initial states and inputs.

        Returns:
            torch.Tensor: The mean squared residual loss scaled by f_sc.
        """
        tau = torch.rand(c.shape[0], 1) * H
        r1, r2 = model.ode_residual(tau, c)
        return ((r1 / f_sc) ** 2 + (r2 / f_sc) ** 2).mean()

    n_tr = len(ctx_tr)
    for ep in range(epochs):
        model.train()
        order = torch.randperm(n_tr)
        running = 0.0
        for b in range(0, n_tr, batch):
            bi = order[b:b + batch]
            c, y = ctx_tr[bi], tgt_tr[bi]
            opt.zero_grad()
            ld = data_loss(c, y)
            lo = ode_loss(c)
            loss = ld + w_ode * lo
            loss.backward()
            opt.step()
            running += loss.item() * len(bi)
        sched.step()
        if verbose and (ep % 25 == 0 or ep == epochs - 1):
            rmse = eval_force_rmse(model, ctx_val, tgt_val, H)
            print(f"  ep {ep:3d}  loss={running / n_tr:.4e}  data={ld.item():.3e}"
                  f"  ode={lo.item():.3e}  val force RMSE={rmse:.2f} N")

    rmse = eval_force_rmse(model, ctx_val, tgt_val, H)
    torch.save(
        {
            "state_dict": model.state_dict(),
            "cfg": cfg.__dict__,
            "schema_version": 2,
            "actuation": "articulated_frame",
        },
        MODEL_PATH,
    )
    if verbose:
        print(f"\nsaved {MODEL_PATH}  (val contact-force RMSE = {rmse:.2f} N)")
    return {"val_force_rmse_N": rmse, "path": str(MODEL_PATH)}


@torch.no_grad()
def eval_force_rmse(model: PantoPINN, ctx_val: torch.Tensor, tgt_val: torch.Tensor, H: float) -> float:
    """Evaluates the contact-force Root Mean Square Error (RMSE) at tau=H.

    Compares the PINN's predicted contact force against the true contact force calculated
    from the rolled-forward state.

    Args:
        model (PantoPINN): The trained PINN model.
        ctx_val (torch.Tensor): Validation context tensor containing initial states, controls, and wire features.
        tgt_val (torch.Tensor): Validation target tensor containing the true next states.
        H (float): The prediction horizon.

    Returns:
        float: The contact-force RMSE in Newtons.
    """
    tau = torch.full((ctx_val.shape[0], 1), H)
    f_pred = model.contact_force(tau, ctx_val)
    yw = model.wire(tau, ctx_val)
    f_true = torch.relu(model.panto.kc * (tgt_val[:, 0:1] - yw))
    return float(torch.sqrt(((f_pred - f_true) ** 2).mean()).item())


if __name__ == "__main__":
    train()
