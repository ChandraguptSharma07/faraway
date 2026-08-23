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
    """Pre-computed modal parameters for a real-time catenary simulation.
    
    Attributes:
        params: The distributed catenary physical parameters.
        modes: Matrix of mass-normalized eigenvectors for the wire structure.
        mass_diagonal: The diagonal of the assembled mass matrix.
        omega_squared: Array of squared angular frequencies for the retained modes.
        modal_damping: Array of modal damping coefficients.
        dropper_vectors: Transformation matrix to calculate dropper extensions from physical DOFs.
        contact_wave_speed: Transverse wave speed along the contact wire (m/s).
        messenger_wave_speed: Transverse wave speed along the messenger wire (m/s).
    """
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
        """int: The number of nodes per wire in the finite element mesh."""
        return self.params.n_nodes

    @property
    def ndof(self) -> int:
        """int: Total number of physical degrees of freedom (2 * n_nodes)."""
        return 2 * self.n_nodes

    @property
    def mode_count(self) -> int:
        """int: The number of modes retained in the modal basis."""
        return self.modes.shape[1]


@dataclass(frozen=True)
class CatenaryPreview:
    """State preview resulting from a single integration step for implicit iteration.
    
    Attributes:
        displacement: Modal displacement vector at the end of the step.
        velocity: Modal velocity vector at the end of the step.
        acceleration: Modal acceleration vector at the end of the step.
        position: Longitudinal position of the pantograph at the end of the step.
        contact_displacement: Physical upward displacement of the contact point.
        contact_velocity: Physical upward velocity of the contact point.
    """
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
    """Assembles the finite element system and extracts a truncated modal basis.
    
    Args:
        params: Distributed catenary parameters. If None, defaults to 8 spans.
        panto: Pantograph parameters (optional, may affect assembled mass).
        mode_count: Maximum number of lowest-frequency modes to retain.
        
    Returns:
        A frozen RealtimeCatenaryModel containing the extracted modal parameters.
    """
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
    """Independent dynamic wire state for one pantograph/control lane.
    
    Attributes:
        model: The underlying pre-computed real-time model.
        dt: Time step for integration (seconds).
        reference_force: The baseline steady contact force (N).
        displacement: Current modal displacement vector.
        velocity: Current modal velocity vector.
        acceleration: Current modal acceleration vector.
        position: Current longitudinal position of the pantograph.
        distance_travelled: Total distance the pantograph has travelled.
        last_contact_force: Most recent contact force applied.
        last_coupling_residual: Residual error in force coupling.
        shift_count: Number of times the spatial window has been shifted.
    """

    def __init__(
        self,
        model: RealtimeCatenaryModel,
        dt: float,
        reference_force: float = 115.0,
    ):
        """Initializes the real-time catenary dynamic state.
        
        Args:
            model: The base physical and modal properties.
            dt: The integration time step in seconds. Must be positive.
            reference_force: Steady uplift preload force in Newtons.
            
        Raises:
            ValueError: If dt is not positive.
        """
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
        """Calculates element interpolation weights for a given position.
        
        Args:
            position: The longitudinal coordinate. Defaults to current position.
            
        Returns:
            A tuple containing node indices and the interpolation weight array.
        """
        return interpolation_weights(
            self.position if position is None else position,
            self.model.params.dx,
            self.model.n_nodes,
        )

    def reproject_model(self, model: RealtimeCatenaryModel) -> None:
        """Preserves physical wire state while tension changes the modal basis.
        
        Args:
            model: The new RealtimeCatenaryModel to project the physical state onto.
            
        Raises:
            ValueError: If the new model does not match the mesh size of the current model.
        """
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
        """Calculates the physical displacement of the contact wire at the current position.
        
        Returns:
            The displacement in meters.
        """
        return float(self._contact_shape(self.position) @ self.displacement)

    def contact_velocity(self) -> float:
        """Calculates the physical velocity of the contact wire at the current position.
        
        Returns:
            The velocity in m/s.
        """
        return float(self._contact_shape(self.position) @ self.velocity)

    def contact_acceleration(self) -> float:
        """Calculates the physical acceleration of the contact wire at the current position.
        
        Returns:
            The acceleration in m/s^2.
        """
        return float(self._contact_shape(self.position) @ self.acceleration)

    def initialize_static(self, contact_force: float) -> None:
        """Initializes the modal state to the static equilibrium under a given contact force.
        
        Args:
            contact_force: The constant uplift force applied to the contact wire (N).
        """
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
        """Calculates the static vertical compliance of the wire at the current position.
        
        Returns:
            The compliance (displacement per unit force) in m/N.
        """
        shape = self._contact_shape(self.position)
        return float(np.sum(shape * shape / self.model.omega_squared))

    def _contact_shape(self, position: float) -> np.ndarray:
        """Calculates the modal shape vector interpolated at a specific longitudinal position.
        
        Args:
            position: The longitudinal coordinate along the span (meters).
            
        Returns:
            The interpolated modal shape vector.
        """
        nodes, weights = self._weights(position)
        return weights @ self.model.modes[nodes]

    def _modal_contact_load(self, force: float, position: float) -> np.ndarray:
        """Projects a physical point force at a given position into modal coordinates.
        
        Args:
            force: The applied physical upward force (N).
            position: The longitudinal coordinate of the applied force (meters).
            
        Returns:
            The modal load vector.
        """
        return float(force) * self._contact_shape(position)

    def _modal_acceleration(self, displacement, velocity, load):
        """Calculates modal acceleration given the system state and applied modal load.
        
        Args:
            displacement: Modal displacement vector.
            velocity: Modal velocity vector.
            load: Modal load vector.
            
        Returns:
            The resulting modal acceleration vector.
        """
        return (
            load
            - self.model.modal_damping * velocity
            - self.model.omega_squared * displacement
        )

    def _shift_window_if_needed(self) -> None:
        """Shifts the spatial coordinate window backwards to prevent periodic wrap-around.
        
        If the current position exceeds 4.5 span lengths, the underlying physical
        degrees of freedom are translated backwards by one full span length, and the
        modal state is re-projected accordingly.
        """
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
        """Predicts one step without mutation for implicit contact iteration.
        
        Uses the average-acceleration Newmark method for unconditionally stable integration.
        
        Args:
            contact_force: The upward force applied to the contact wire (N).
            speed_ms: The speed of the pantograph along the wire (m/s).
            
        Returns:
            A CatenaryPreview containing the predicted modal and physical states.
        """
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
        """Vectorized modal step used by catenary-aware MPC rollouts.
        
        Allows computing multiple candidate futures simultaneously in a vectorized manner.
        
        Args:
            displacement: Current modal displacement array.
            velocity: Current modal velocity array.
            acceleration: Current modal acceleration array.
            contact_forces: Array of candidate contact forces to apply (N).
            position: Current longitudinal position (meters).
            speed_ms: The speed of the pantograph (m/s).
            interval: The time step interval (seconds).
            
        Returns:
            A tuple of (next_displacement, next_velocity, next_acceleration,
            next_position, contact_displacement, contact_velocity, contact_acceleration).
        """
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
        """Commits a previewed state to become the current state of the wire.
        
        Args:
            preview: The previewed state to commit.
            contact_force: The contact force used to generate this preview.
            speed_ms: The travel speed used to generate this preview.
            
        Returns:
            The resulting physical upward displacement of the contact point.
        """
        self.displacement = preview.displacement
        self.velocity = preview.velocity
        self.acceleration = preview.acceleration
        self.position = preview.position
        self.distance_travelled += speed_ms * self.dt
        self.last_contact_force = float(max(contact_force, 0.0))
        self._shift_window_if_needed()
        return self.contact_displacement()

    def step(self, contact_force: float, speed_ms: float) -> float:
        """Advances one integration step; use preview/commit for coupled plant integration.
        
        Args:
            contact_force: Applied upward force (N).
            speed_ms: Travel speed (m/s).
            
        Returns:
            The resulting physical upward displacement of the contact point.
        """
        return self.commit(self.preview(contact_force, speed_ms), contact_force, speed_ms)

    def telemetry(self) -> dict:
        """Gathers runtime diagnostics for this catenary lane.
        
        Returns:
            A dictionary containing structural telemetry metrics like peak deflection,
            contact wire ripple, and slack dropper risks.
        """
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
    """Plant environment: shared exogenous field plus lane-specific wire motion.
    
    Provides an interface matching the base kinematic environment but includes
    the dynamic "ripple" (deflection and velocity) of the real-time catenary wire.
    
    Attributes:
        base: The base steady-state kinematic environment.
        wire: The dynamic RealtimeCatenary instance for this lane.
        cat: The catenary parameters (from base environment).
        ripple_override: Optional override for contact wire displacement (meters).
        ripple_velocity_override: Optional override for contact wire velocity (m/s).
    """

    def __init__(self, base, wire: RealtimeCatenary):
        """Initializes the coupled wire environment.
        
        Args:
            base: The static or kinematic environment providing the steady baseline.
            wire: The dynamic catenary model calculating the interactive ripple.
        """
        self.base = base
        self.wire = wire
        self.cat = base.cat
        self.ripple_override: float | None = None
        self.ripple_velocity_override: float | None = None

    def y_wire(self, t, speed_ms: float, beyond: BeyondEnvelope):
        """Calculates the total vertical position of the contact wire.
        
        Args:
            t: Current time (seconds).
            speed_ms: Travel speed (m/s).
            beyond: Envelope violation flag/state.
            
        Returns:
            The vertical position of the wire (meters).
        """
        ripple = (
            self.wire.contact_displacement()
            if self.ripple_override is None
            else self.ripple_override
        )
        return self.base.y_wire(t, speed_ms, beyond) + ripple

    def aero_force(self, speed_ms: float, beyond: BeyondEnvelope) -> float:
        """Calculates aerodynamic uplift force on the pantograph.
        
        Args:
            speed_ms: Travel speed (m/s).
            beyond: Envelope violation flag/state.
            
        Returns:
            The aerodynamic force (N).
        """
        return self.base.aero_force(speed_ms, beyond)

    def wire_velocity(self, t, speed_ms: float, beyond: BeyondEnvelope) -> float:
        """Calculates the total vertical velocity of the contact wire.
        
        Args:
            t: Current time (seconds).
            speed_ms: Travel speed (m/s).
            beyond: Envelope violation flag/state.
            
        Returns:
            The vertical velocity of the wire (m/s).
        """
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
        """Calculates the instantaneous interaction force between pantograph and wire.
        
        Args:
            t: Current time (seconds).
            speed_ms: Travel speed (m/s).
            beyond: Envelope violation flag/state.
            head_position: Vertical position of the pantograph head (meters).
            head_velocity: Vertical velocity of the pantograph head (m/s).
            contact_stiffness: Stiffness of the contact strip (N/m).
            
        Returns:
            The interaction force (N), guaranteed non-negative (loss of contact = 0).
        """
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
