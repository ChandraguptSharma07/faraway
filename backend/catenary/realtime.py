"""Real-time moving-window reduction of the distributed catenary.

The live model retains the contact and messenger-wire DOFs assembled by the
distributed reference model, but linearises droppers about their taut operating
point and advances retained modes with Newmark integration. A moving spatial window prevents artificial
periodic wrap-around during an indefinitely running dashboard.

Positive displacement and contact force are upward on the wire.  Pantograph force
therefore changes the wire state, and that changed wire height feeds back into the
next pantograph contact-force calculation.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

import numpy as np
from scipy import linalg

from backend.sim.parameters import BeyondEnvelope, PantographParams

from .model import assemble_system, interpolation_weights
from .parameters import DistributedCatenaryParams


@dataclass(frozen=True)
class RealtimeCatenaryModel:
    params: DistributedCatenaryParams
    modes: np.ndarray
    mass_diagonal: np.ndarray
    omega_squared: np.ndarray
    modal_damping: np.ndarray
    dropper_vectors: np.ndarray
    contact_wave_speed: float
    messenger_wave_speed: float

    @property
    def n_nodes(self) -> int:
        return self.params.n_nodes

    @property
    def ndof(self) -> int:
        return 2 * self.n_nodes

    @property
    def mode_count(self) -> int:
        return self.modes.shape[1]


@dataclass(frozen=True)
class CatenaryPreview:
    displacement: np.ndarray
    velocity: np.ndarray
    acceleration: np.ndarray
    position: float
    contact_displacement: float
    contact_velocity: float


def build_realtime_model(
    params: DistributedCatenaryParams | None = None,
    panto: PantographParams | None = None,
    mode_count: int = 36,
) -> RealtimeCatenaryModel:
    # Eight spans keep boundaries several wave-flight times from the moving contact
    # while remaining cheap enough for three independently coupled live lanes.
    params = params or replace(DistributedCatenaryParams(), n_spans=8)
    system = assemble_system(params, panto)
    n = system.n_wire
    stiffness, _, _ = system.active_structure(np.zeros(system.ndof))
    mass_diag = np.diag(system.M)[: 2 * n]
    wire_k = stiffness[: 2 * n, : 2 * n]
    wire_c = system.C[: 2 * n, : 2 * n]
    eigenvalues, modes = linalg.eigh(
        wire_k,
        np.diag(mass_diag),
        subset_by_index=(0, min(mode_count, 2 * n) - 1),
    )
    keep = eigenvalues > 1.0e-8
    eigenvalues, modes = eigenvalues[keep], modes[:, keep]
    modal_c = modes.T @ wire_c @ modes
    return RealtimeCatenaryModel(
        params=params,
        modes=modes,
        mass_diagonal=mass_diag,
        omega_squared=eigenvalues,
        modal_damping=np.diag(modal_c),
        dropper_vectors=np.stack([
            vector[: 2 * n] for vector in system.dropper_vectors
        ]),
        contact_wave_speed=float(
            np.sqrt(params.contact_tension / params.contact_mass_per_m)
        ),
        messenger_wave_speed=float(
            np.sqrt(params.messenger_tension / params.messenger_mass_per_m)
        ),
    )


class RealtimeCatenary:
    """Independent dynamic wire state for one pantograph/control lane."""

    def __init__(
        self,
        model: RealtimeCatenaryModel,
        dt: float,
        reference_force: float = 115.0,
    ):
        if dt <= 0.0:
            raise ValueError("dt must be positive")
        self.model = model
        self.dt = dt
        self.reference_force = float(reference_force)
        self.displacement = np.zeros(model.mode_count)
        self.velocity = np.zeros(model.mode_count)
        self.acceleration = np.zeros(model.mode_count)
        self.position = 3.5 * model.params.span_length
        self.distance_travelled = 0.0
        self.last_contact_force = self.reference_force
        self.last_coupling_residual = 0.0
        self.shift_count = 0

    def _weights(self, position: float | None = None):
        return interpolation_weights(
            self.position if position is None else position,
            self.model.params.dx,
            self.model.n_nodes,
        )

    def reproject_model(self, model: RealtimeCatenaryModel) -> None:
        """Preserve physical wire state while tension changes the modal basis."""
        if model.ndof != self.model.ndof:
            raise ValueError("replacement catenary model must keep the same mesh")
        physical_u = self.model.modes @ self.displacement
        physical_v = self.model.modes @ self.velocity
        self.model = model
        weighted_modes = model.modes.T * model.mass_diagonal
        self.displacement = weighted_modes @ physical_u
        self.velocity = weighted_modes @ physical_v
        load = self._modal_contact_load(
            self.last_contact_force - self.reference_force, self.position
        )
        self.acceleration = self._modal_acceleration(
            self.displacement, self.velocity, load
        )

    def contact_displacement(self) -> float:
        return float(self._contact_shape(self.position) @ self.displacement)

    def contact_velocity(self) -> float:
        return float(self._contact_shape(self.position) @ self.velocity)

    def contact_acceleration(self) -> float:
        return float(self._contact_shape(self.position) @ self.acceleration)

    def initialize_static(self, contact_force: float) -> None:
        load = self._modal_contact_load(
            float(contact_force) - self.reference_force, self.position
        )
        self.displacement = load / self.model.omega_squared
        self.velocity.fill(0.0)
        self.acceleration = self._modal_acceleration(
            self.displacement, self.velocity, load
        )
        self.last_contact_force = float(max(contact_force, 0.0))

    def static_compliance(self) -> float:
        shape = self._contact_shape(self.position)
        return float(np.sum(shape * shape / self.model.omega_squared))

    def _contact_shape(self, position: float) -> np.ndarray:
        nodes, weights = self._weights(position)
        return weights @ self.model.modes[nodes]

    def _modal_contact_load(self, force: float, position: float) -> np.ndarray:
        return float(force) * self._contact_shape(position)

    def _modal_acceleration(self, displacement, velocity, load):
        return (
            load
            - self.model.modal_damping * velocity
            - self.model.omega_squared * displacement
        )

    def _shift_window_if_needed(self) -> None:
        p = self.model.params
        upper = 4.5 * p.span_length
        if self.position < upper:
            return
        count = p.elements_per_span
        n = self.model.n_nodes
        physical_u = self.model.modes @ self.displacement
        physical_v = self.model.modes @ self.velocity
        for field in (physical_u, physical_v):
            for offset in (0, n):
                block = field[offset : offset + n]
                block[:-count] = block[count:]
                block[-count:] = 0.0
        weighted_modes = self.model.modes.T * self.model.mass_diagonal
        self.displacement = weighted_modes @ physical_u
        self.velocity = weighted_modes @ physical_v
        self.acceleration = self._modal_acceleration(
            self.displacement, self.velocity, np.zeros(self.model.mode_count)
        )
        self.position -= p.span_length
        self.shift_count += 1

    def preview(self, contact_force: float, speed_ms: float) -> CatenaryPreview:
        """Predict one step without mutation for implicit contact iteration."""
        midpoint = self.position + 0.5 * speed_ms * self.dt
        # Coordinates are perturbations about the static 115 N uplifted state.
        # Negative modal load means less uplift than that preload, not a wire that
        # physically pulls the pantograph downward.
        dynamic_force = float(contact_force) - self.reference_force
        load = self._modal_contact_load(dynamic_force, midpoint)

        # Average-acceleration Newmark is unconditionally stable for this linear
        # modal system. All retained modes remain dynamic; truncation removes only
        # spatial frequencies the live 1 ms loop cannot credibly resolve.
        beta, gamma = 0.25, 0.5
        predicted_u = (
            self.displacement
            + self.dt * self.velocity
            + self.dt * self.dt * (0.5 - beta) * self.acceleration
        )
        predicted_v = self.velocity + self.dt * (1.0 - gamma) * self.acceleration
        effective = (
            1.0
            + gamma * self.dt * self.model.modal_damping
            + beta * self.dt * self.dt * self.model.omega_squared
        )
        next_acceleration = (
            load
            - self.model.modal_damping * predicted_v
            - self.model.omega_squared * predicted_u
        ) / effective
        next_displacement = predicted_u + beta * self.dt * self.dt * next_acceleration
        next_velocity = predicted_v + gamma * self.dt * next_acceleration

        next_position = self.position + speed_ms * self.dt
        shape = self._contact_shape(next_position)
        return CatenaryPreview(
            displacement=next_displacement,
            velocity=next_velocity,
            acceleration=next_acceleration,
            position=next_position,
            contact_displacement=float(shape @ next_displacement),
            contact_velocity=float(shape @ next_velocity),
        )

    def preview_candidates(
        self,
        displacement: np.ndarray,
        velocity: np.ndarray,
        acceleration: np.ndarray,
        contact_forces: np.ndarray,
        position: float,
        speed_ms: float,
        interval: float,
    ):
        """Vectorized modal step used by catenary-aware MPC rollouts."""
        q = np.asarray(displacement, dtype=float)
        v = np.asarray(velocity, dtype=float)
        a = np.asarray(acceleration, dtype=float)
        forces = np.asarray(contact_forces, dtype=float)
        midpoint = position + 0.5 * speed_ms * interval
        shape_mid = self._contact_shape(midpoint)
        load = (forces - self.reference_force)[:, None] * shape_mid[None, :]
        beta, gamma = 0.25, 0.5
        predicted_q = q + interval * v + interval * interval * (0.5 - beta) * a
        predicted_v = v + interval * (1.0 - gamma) * a
        effective = (
            1.0
            + gamma * interval * self.model.modal_damping
            + beta * interval * interval * self.model.omega_squared
        )
        next_a = (
            load
            - self.model.modal_damping[None, :] * predicted_v
            - self.model.omega_squared[None, :] * predicted_q
        ) / effective[None, :]
        next_q = predicted_q + beta * interval * interval * next_a
        next_v = predicted_v + gamma * interval * next_a
        next_position = position + speed_ms * interval
        shape_next = self._contact_shape(next_position)
        return (
            next_q,
            next_v,
            next_a,
            next_position,
            next_q @ shape_next,
            next_v @ shape_next,
            next_a @ shape_next,
        )

    def commit(self, preview: CatenaryPreview, contact_force: float, speed_ms: float):
        self.displacement = preview.displacement
        self.velocity = preview.velocity
        self.acceleration = preview.acceleration
        self.position = preview.position
        self.distance_travelled += speed_ms * self.dt
        self.last_contact_force = float(max(contact_force, 0.0))
        self._shift_window_if_needed()
        return self.contact_displacement()

    def step(self, contact_force: float, speed_ms: float) -> float:
        """Advance one step; use preview/commit for coupled plant integration."""
        return self.commit(self.preview(contact_force, speed_ms), contact_force, speed_ms)

    def telemetry(self) -> dict:
        n = self.model.n_nodes
        p = self.model.params
        physical = self.model.modes @ self.displacement
        contact = physical[:n]
        messenger = physical[n:]
        dropper_extension = self.model.dropper_vectors @ physical
        slack_threshold = -p.dropper_preload / p.dropper_stiffness
        return {
            "contact_ripple_mm": round(1e3 * self.contact_displacement(), 3),
            "contact_velocity_mm_s": round(1e3 * self.contact_velocity(), 3),
            "peak_contact_wire_mm": round(1e3 * float(np.max(np.abs(contact))), 3),
            "peak_messenger_wire_mm": round(1e3 * float(np.max(np.abs(messenger))), 3),
            "linearized_slack_risk_droppers": int(
                np.sum(dropper_extension < slack_threshold)
            ),
            "window_shifts": self.shift_count,
            "retained_modes": self.model.mode_count,
            "coupling_residual_N": round(self.last_coupling_residual, 3),
        }


class CoupledWireEnvironment:
    """Plant environment: shared exogenous field plus lane-specific wire motion."""

    def __init__(self, base, wire: RealtimeCatenary):
        self.base = base
        self.wire = wire
        self.cat = base.cat
        self.ripple_override: float | None = None
        self.ripple_velocity_override: float | None = None

    def y_wire(self, t, speed_ms: float, beyond: BeyondEnvelope):
        ripple = (
            self.wire.contact_displacement()
            if self.ripple_override is None
            else self.ripple_override
        )
        return self.base.y_wire(t, speed_ms, beyond) + ripple

    def aero_force(self, speed_ms: float, beyond: BeyondEnvelope) -> float:
        return self.base.aero_force(speed_ms, beyond)

    def wire_velocity(self, t, speed_ms: float, beyond: BeyondEnvelope) -> float:
        base_velocity = self.base.wire_velocity(t, speed_ms, beyond)
        ripple_velocity = (
            self.wire.contact_velocity()
            if self.ripple_velocity_override is None
            else self.ripple_velocity_override
        )
        return base_velocity + ripple_velocity

    def contact_force(
        self,
        t: float,
        speed_ms: float,
        beyond: BeyondEnvelope,
        head_position: float,
        head_velocity: float,
        contact_stiffness: float,
    ) -> float:
        base_position, base_velocity = self.base.wire_kinematics(
            t, speed_ms, beyond
        )
        ripple = (
            self.wire.contact_displacement()
            if self.ripple_override is None
            else self.ripple_override
        )
        ripple_velocity = (
            self.wire.contact_velocity()
            if self.ripple_velocity_override is None
            else self.ripple_velocity_override
        )
        gap = head_position - (base_position + ripple)
        relative_velocity = head_velocity - (base_velocity + ripple_velocity)
        force = (
            contact_stiffness * gap
            + self.wire.model.params.contact_damping * relative_velocity
        )
        return max(float(force), 0.0)
