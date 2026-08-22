"""Physically-defensible catenary disturbance model (NOT a plain sine).

y_wire(t) is the effective vertical trajectory of the contact wire that the
collector head follows, built from three named components:

  (a) SPAN-PASSING  — the wire sags mid-span and rises/stiffens near support poles.
                      Temporal frequency f_span = v / span_length SCALES with speed.
  (b) AERODYNAMIC   — uplift force on the head, F_aero = c_aero * v^2 (returned
                      separately as a force, applied in the EOM).
  (c) TURBULENCE    — band-limited stochastic noise (sum of random-phase sinusoids,
                      reproducible via a fixed seed).

Beyond-envelope knobs (degraded tension, amplified turbulence, gust) leave the
validated regime untouched at their neutral defaults.
"""

from __future__ import annotations

import numpy as np

from .parameters import BeyondEnvelope, CatenaryParams


class Disturbance:
    """Model representing the physical disturbances on a catenary system."""
    
    def __init__(
        self,
        cat: CatenaryParams,
        n_turb: int = 48,
        seed: int = 12345,
    ) -> None:
        """Initialize the Disturbance model.

        Args:
            cat (CatenaryParams): Parameters of the catenary system.
            n_turb (int, optional): Number of turbulence components. Defaults to 48.
            seed (int, optional): Random seed for reproducible turbulence. Defaults to 12345.
        """
        self.cat = cat
        rng = np.random.default_rng(seed)
        # Band-limited turbulence as a sum of n_turb random-phase sinusoids spread
        # across (0, turb_fmax]. Per-component amplitude chosen so the aggregate std
        # equals turb_std: std of sum of N random-phase sinusoids of amp a is a*sqrt(N/2).
        self._turb_f = np.linspace(0.7, cat.turb_fmax, n_turb)
        self._turb_omega = 2.0 * np.pi * self._turb_f
        self._turb_phase = rng.uniform(0.0, 2.0 * np.pi, n_turb)
        self._turb_amp = cat.turb_std * np.sqrt(2.0 / n_turb)
        # Phase offset so the support-passing reference (x=0) starts at a support.
        self._x0 = 0.0

    # --- components ---------------------------------------------------------
    def y_span(self, t, speed_ms: float, beyond: BeyondEnvelope) -> np.ndarray | float:
        """Calculate the span-passing wire height, peaking at supports and sagging mid-span.

        Args:
            t (float or np.ndarray): Time in seconds.
            speed_ms (float): Speed of the train in meters per second.
            beyond (BeyondEnvelope): Beyond-envelope parameters including tension factor.

        Returns:
            np.ndarray | float: The span-passing wire height at time t.
        """
        if getattr(t, "ndim", 0) == 0:
            x = speed_ms * t + self._x0
            L = self.cat.span_length
            amp = self.cat.a_span / max(beyond.tension_factor, 1e-3)
            amp2 = self.cat.a_span2 / max(beyond.tension_factor, 1e-3)
            arg = 2 * np.pi * x / L
            return amp * np.cos(arg) + amp2 * np.cos(2 * arg)
        x = speed_ms * np.asarray(t) + self._x0
        L = self.cat.span_length
        amp = self.cat.a_span / max(beyond.tension_factor, 1e-3)
        amp2 = self.cat.a_span2 / max(beyond.tension_factor, 1e-3)
        arg = 2 * np.pi * x / L
        return amp * np.cos(arg) + amp2 * np.cos(2 * arg)

    def y_turb(self, t, beyond: BeyondEnvelope) -> np.ndarray | float:
        """Calculate the band-limited turbulence.

        Args:
            t (float or np.ndarray): Time in seconds.
            beyond (BeyondEnvelope): Beyond-envelope parameters including turbulence gain.

        Returns:
            np.ndarray | float: The turbulence in meters of equivalent wire displacement.
        """
        gain = beyond.turbulence_gain
        if getattr(t, "ndim", 0) == 0:
            phases = self._turb_omega * t + self._turb_phase
            return float(self._turb_amp * np.sin(phases).sum() * gain)
        # Broadcast: sum over turbulence components.
        t_arr = np.asarray(t)
        phases = np.outer(t_arr, self._turb_omega) + self._turb_phase
        return self._turb_amp * np.sin(phases).sum(axis=-1) * gain

    def y_wire(self, t, speed_ms: float, beyond: BeyondEnvelope) -> np.ndarray | float:
        """Calculate the total effective wire vertical trajectory the head follows.

        Args:
            t (float or np.ndarray): Time in seconds.
            speed_ms (float): Speed of the train in meters per second.
            beyond (BeyondEnvelope): Beyond-envelope parameters.

        Returns:
            np.ndarray | float: Total effective wire height at time t.
        """
        return self.y_span(t, speed_ms, beyond) + self.y_turb(t, beyond)

    def wire_kinematics(
        self,
        t: float,
        speed_ms: float,
        beyond: BeyondEnvelope,
    ) -> tuple[float, float]:
        """Calculate the scalar wire displacement and its exact time derivative.

        The coupled solver needs both values at every force evaluation. Computing
        them together avoids repeating the turbulence sum and removes the finite-
        difference approximation previously used for wire velocity.

        Args:
            t (float): Time in seconds.
            speed_ms (float): Speed of the train in meters per second.
            beyond (BeyondEnvelope): Beyond-envelope parameters.

        Returns:
            tuple[float, float]: A tuple of (wire_displacement, wire_velocity).
        """
        x = speed_ms * float(t) + self._x0
        tension = max(beyond.tension_factor, 1.0e-3)
        amp = self.cat.a_span / tension
        amp2 = self.cat.a_span2 / tension
        span_omega = 2.0 * np.pi * speed_ms / self.cat.span_length
        arg = 2.0 * np.pi * x / self.cat.span_length
        span = amp * np.cos(arg) + amp2 * np.cos(2.0 * arg)
        span_velocity = (
            -amp * span_omega * np.sin(arg)
            - 2.0 * amp2 * span_omega * np.sin(2.0 * arg)
        )

        phases = self._turb_omega * float(t) + self._turb_phase
        gain = beyond.turbulence_gain
        turbulence = self._turb_amp * np.sin(phases).sum() * gain
        turbulence_velocity = (
            self._turb_amp * (self._turb_omega * np.cos(phases)).sum() * gain
        )
        return float(span + turbulence), float(span_velocity + turbulence_velocity)

    def wire_velocity(
        self,
        t: float,
        speed_ms: float,
        beyond: BeyondEnvelope,
    ) -> float:
        """Calculate the exact scalar time derivative of the wire displacement.

        Args:
            t (float): Time in seconds.
            speed_ms (float): Speed of the train in meters per second.
            beyond (BeyondEnvelope): Beyond-envelope parameters.

        Returns:
            float: The wire velocity at time t.
        """
        return self.wire_kinematics(t, speed_ms, beyond)[1]

    def aero_force(self, speed_ms: float, beyond: BeyondEnvelope) -> float:
        """Calculate the aerodynamic uplift force on the head.

        Args:
            speed_ms (float): Speed of the train in meters per second.
            beyond (BeyondEnvelope): Beyond-envelope parameters including gust.

        Returns:
            float: The aerodynamic uplift force in Newtons.
        """
        return self.cat.c_aero * speed_ms * speed_ms + beyond.gust
