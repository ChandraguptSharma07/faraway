"""Physics-Informed Neural Network — a short-horizon contact-force PREDICTOR.

The PINN is NOT the controller. It answers: "given the current state, the local
disturbance, aerodynamic head force, and applied frame force, what does the
pantograph do over the next few milliseconds?" A separate controller
(backend/controller/) queries it.

Formulation (time-continuous over a short horizon tau in [0, H]):

  context c = [z1, z1', z2, z2', f_aero, f_frame, y0, y0', y0'']
  network   n_theta(tau, c) -> (n1, n2)
  trajectory (hard initial-condition constraint, exact position AND velocity at tau=0):
      z1(tau) = z1_0 + z1'_0 * tau + tau^2 * A * n1
      z2(tau) = z2_0 + z2'_0 * tau + tau^2 * A * n2

The contact force is derived physically: P(tau) = relu(kc * (z1(tau) - y_wire(tau))),
with y_wire(tau) = y0 + y0'*tau + 0.5*y0''*tau^2 (local quadratic extrapolation; valid
because H is a few ms, far shorter than every disturbance period).

Physics-informed loss: the second time-derivatives of z1, z2 (via autograd in tau) are
fed back through the EN 50318 EOM and the residual is penalized (L_ode); supervised
agreement with the classical solver at tau=H is L_data.
"""

from __future__ import annotations

from dataclasses import dataclass

import torch
import torch.nn as nn

from backend.sim.parameters import PantographParams

# Characteristic scales for input normalization (keep the MLP well-conditioned).
SCALE = {
    "z": 0.06,      # m   displacement
    "zd": 0.7,      # m/s velocity
    "f": 120.0,     # N   head force
    "y": 0.06,      # m   wire position
    "yd": 0.7,      # m/s wire velocity
    "ydd": 12.0,    # m/s^2 wire acceleration
}
ACCEL_SCALE = 20.0  # maps the tau^2 network term to a physical acceleration scale (m/s^2)


@dataclass(frozen=True)
class PinnConfig:
    horizon: float = 5.0e-3   # s   prediction horizon H
    hidden: int = 64
    depth: int = 3


def context_from(z1, z1d, z2, z2d, f_aero, f_frame, y0, y0d, y0dd) -> torch.Tensor:
    """Assemble a (…, 9) context tensor from raw physical quantities."""
    return torch.stack(
        [
            torch.as_tensor(z1), torch.as_tensor(z1d),
            torch.as_tensor(z2), torch.as_tensor(z2d),
            torch.as_tensor(f_aero), torch.as_tensor(f_frame),
            torch.as_tensor(y0), torch.as_tensor(y0d), torch.as_tensor(y0dd),
        ],
        dim=-1,
    ).float()


class PantoPINN(nn.Module):
    def __init__(self, cfg: PinnConfig | None = None, panto: PantographParams | None = None):
        super().__init__()
        self.cfg = cfg or PinnConfig()
        self.panto = panto or PantographParams()

        layers: list[nn.Module] = [nn.Linear(10, self.cfg.hidden), nn.Tanh()]
        for _ in range(self.cfg.depth - 1):
            layers += [nn.Linear(self.cfg.hidden, self.cfg.hidden), nn.Tanh()]
        layers += [nn.Linear(self.cfg.hidden, 2)]
        self.net = nn.Sequential(*layers)

        # Normalization vector for the 9-dim context (registered, not trained).
        s = SCALE
        self.register_buffer(
            "ctx_scale",
            torch.tensor([s["z"], s["zd"], s["z"], s["zd"], s["f"], s["f"], s["y"], s["yd"], s["ydd"]]),
        )

    def _raw(self, tau: torch.Tensor, ctx: torch.Tensor) -> torch.Tensor:
        tau_n = tau / self.cfg.horizon
        ctx_n = ctx / self.ctx_scale
        return self.net(torch.cat([tau_n, ctx_n], dim=-1))

    def trajectory(self, tau: torch.Tensor, ctx: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
        """Return (z1(tau), z2(tau)) with the hard IC constraint applied."""
        n = self._raw(tau, ctx)
        z1_0, z1d_0, z2_0, z2d_0 = ctx[..., 0:1], ctx[..., 1:2], ctx[..., 2:3], ctx[..., 3:4]
        t2 = tau * tau
        z1 = z1_0 + z1d_0 * tau + t2 * ACCEL_SCALE * n[..., 0:1]
        z2 = z2_0 + z2d_0 * tau + t2 * ACCEL_SCALE * n[..., 1:2]
        return z1, z2

    def wire(self, tau: torch.Tensor, ctx: torch.Tensor) -> torch.Tensor:
        y0, y0d, y0dd = ctx[..., 6:7], ctx[..., 7:8], ctx[..., 8:9]
        return y0 + y0d * tau + 0.5 * y0dd * tau * tau

    def contact_force(self, tau: torch.Tensor, ctx: torch.Tensor) -> torch.Tensor:
        z1, _ = self.trajectory(tau, ctx)
        yw = self.wire(tau, ctx)
        return torch.relu(self.panto.kc * (z1 - yw))

    def forward(self, tau: torch.Tensor, ctx: torch.Tensor) -> torch.Tensor:
        """Predicted contact force at tau (alias for contact_force)."""
        return self.contact_force(tau, ctx)

    # --- physics residual (autograd in tau) --------------------------------
    def ode_residual(self, tau: torch.Tensor, ctx: torch.Tensor):
        """EN 50318 EOM residuals using autograd second derivatives of z1, z2."""
        tau = tau.clone().requires_grad_(True)
        z1, z2 = self.trajectory(tau, ctx)

        def d_dt(y):
            return torch.autograd.grad(y, tau, torch.ones_like(y), create_graph=True)[0]

        z1d, z2d = d_dt(z1), d_dt(z2)
        z1dd, z2dd = d_dt(z1d), d_dt(z2d)

        p = self.panto  # noqa
        yw = self.wire(tau, ctx)
        P = torch.relu(self.panto.kc * (z1 - yw))
        f_aero = ctx[..., 4:5]
        f_frame = ctx[..., 5:6]

        res1 = (
            self.panto.m1 * z1dd
            + self.panto.r1 * (z1d - z2d)
            + self.panto.k1 * (z1 - z2)
            + P
            - f_aero
        )
        res2 = (
            self.panto.m2 * z2dd
            + self.panto.r2 * z2d
            + self.panto.k2 * z2
            + self.panto.r1 * (z2d - z1d)
            + self.panto.k1 * (z2 - z1)
            - self.panto.F0
            - f_frame
        )
        # Scale residuals to comparable magnitude (forces in N).
        return res1, res2
