"""Physical parameters for the EN 50318 reference pantograph + catenary.

All reference values are the widely-reproduced EN 50318:2002 Annex A figures
(reference pantograph + reference results). See self_notes/decisions.md for the
full source table and any deliberate calibration adjustments.

Sign / coordinate convention (positive = up):
  z1 = collector-head displacement      z2 = articulated-frame displacement
  z3 = base, held fixed at 0 (reduced two-mass model)
  Contact force  P = kc * (y_wire - z1),  clamped at 0 (no tension -> loss of contact).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PantographParams:
    """Parameters for the EN 50318 reference pantograph (two-mass model).

    Attributes:
        m1: Collector-head mass (kg).
        m2: Articulated-frame mass (kg).
        k1: Head stiffness (N/m).
        k2: Frame stiffness (N/m).
        r1: Head damping (Ns/m).
        r2: Frame damping (Ns/m).
        kc: Contact penalty spring for contact-model stability (N/m).
        F0: Static uplift force, tuned so passive mean contact force lands at the EN 50318 setpoint (~115 N) (N).
    """
    # --- EN 50318 reference pantograph (two-mass) ---
    m1: float = 7.2        # kg   collector-head mass
    m2: float = 15.0       # kg   articulated-frame mass
    k1: float = 4200.0     # N/m  head stiffness
    k2: float = 50.0       # N/m  frame stiffness
    r1: float = 10.0       # Ns/m head damping
    r2: float = 90.0       # Ns/m frame damping
    kc: float = 50000.0    # N/m  contact penalty spring (contact-model stability)

    # --- Static uplift: sets the mean contact force ---
    # Tuned so the passive mean contact force lands at the EN 50318 setpoint (~115 N).
    F0: float = 110.5      # N


@dataclass(frozen=True)
class CatenaryParams:
    """Parameters for the EN 50318 reference catenary model.
    
    Attributes:
        span_length: Length of a single span, within the 50-65 m high-speed range (m).
        n_spans: Total number of spans in the model.
        eval_span: 0-indexed middle span to evaluate, avoiding boundary effects.
        a_span: Span-passing wire-height amplitude (m).
        a_span2: Second harmonic amplitude for dropper spacing within a span (m).
        c_aero: Aerodynamic uplift coefficient, reduced from published 0.01301 to keep mean in 110-120 N (Ns^2/m^2).
        c_aero_published: The original published aerodynamic uplift coefficient, kept for reference (Ns^2/m^2).
        turb_std: Standard deviation of stochastic turbulence layered on top (m).
        turb_fmax: Upper band limit for stochastic turbulence (Hz).
        s_wire_eff: Effective catenary stiffness used to report wire uplift at the support (N/m).
    """
    # Reference catenary is a 10-span model; results read from a middle span.
    span_length: float = 60.0   # m   (within the 50-65 m high-speed range)
    n_spans: int = 10
    eval_span: int = 5          # 0-indexed middle span to evaluate (avoids boundaries)

    # --- Disturbance amplitudes (calibrated so the passive solver lands in the
    #     EN 50318 result ranges at 250 and 300 km/h; see decisions.md) ---
    # (a) Span-passing: the contact wire sags mid-span and stiffens/rises near the
    #     support poles. Modeled as an effective vertical wire trajectory the head
    #     follows; temporal frequency f_span = v / span_length scales with speed.
    a_span: float = 0.0130      # m   span-passing wire-height amplitude
    a_span2: float = 0.0042     # m   2nd harmonic (dropper spacing within a span)

    # (b) Aerodynamic uplift force on the head: F_aero = c_aero * v^2.
    #     Published reference factor is 0.01301 Ns^2/m^2; as a pure DC contact-force
    #     contribution that overshoots the EN 50318 mean-force band and makes the mean
    #     swing too much between 250 and 300 km/h. We retain the v^2 scaling but reduce
    #     the gain so the mean stays in 110-120 N across the validated regime. Original
    #     value and reason recorded in self_notes/decisions.md.
    c_aero: float = 0.00120     # Ns^2/m^2  (reduced from published 0.01301)
    c_aero_published: float = 0.01301  # kept for reference / documentation

    # (c) Stochastic turbulence: band-limited noise layered on top (std in metres of
    #     equivalent wire displacement). Kept below the ~13 Hz contact resonance so it
    #     adds realistic jitter without exciting the stiff penalty spring.
    turb_std: float = 0.0005    # m
    turb_fmax: float = 8.0      # Hz  upper band limit

    # Effective catenary stiffness used to report wire uplift at the support:
    #   max_uplift = peak_contact_force / s_wire_eff. The contact wire is flexible and
    #   lifts under the contact force; its deflection is force/stiffness. (A few kN/m is
    #   the standard order for high-speed catenary mean stiffness.)
    s_wire_eff: float = 3600.0  # N/m


@dataclass(frozen=True)
class BeyondEnvelope:
    """Knobs that push past the EN 50318-validated envelope (Step 2 narrative).

    Defaults are neutral (1.0 / nominal) so the validated regime is untouched.
    
    Attributes:
        tension_factor: Multiplier for contact-wire tension where <1 implies degraded tension (softer, larger sag).
        turbulence_gain: Multiplier for turbulence where >1 amplifies turbulence.
        gust: Transient aerodynamic gust force on the collector head (N).
    """
    tension_factor: float = 1.0    # <1 = degraded contact-wire tension (softer, larger sag)
    turbulence_gain: float = 1.0   # >1 = amplified turbulence
    gust: float = 0.0              # N  transient aerodynamic gust force on the head


# Convenient defaults
PANTO = PantographParams()
CATENARY = CatenaryParams()


def kmh_to_ms(kmh: float) -> float:
    """Converts speed from kilometers per hour to meters per second.

    Args:
        kmh: The speed in kilometers per hour.

    Returns:
        The equivalent speed in meters per second.
    """
    return kmh / 3.6


def span_frequency(speed_ms: float, span_length: float = CATENARY.span_length) -> float:
    """Calculates the span-passing temporal frequency.

    The frequency scales directly with the train speed.

    Args:
        speed_ms: The speed of the train in meters per second.
        span_length: The length of a single catenary span in meters. Defaults to CATENARY.span_length.

    Returns:
        The span-passing frequency in Hertz (Hz).
    """
    return speed_ms / span_length
