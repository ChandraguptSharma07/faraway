"""Parameters and provenance for the distributed vertical catenary.

Reference values follow the 60 m simple-catenary benchmark reproduced in:
  https://doi.org/10.1080/00423114.2022.2085586

Every non-sourced modelling choice is labelled ``assumed`` below.  These assumptions
must be sensitivity-tested and replaced by line/manufacturer data before any claim of
route-specific fidelity.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class DistributedCatenaryParams:
    """Parameters defining a distributed vertical catenary model.

    This class encapsulates the physical, geometric, and numerical properties
    required to simulate a railway catenary system. Default values correspond
    to the 60 m simple-catenary benchmark.

    Attributes:
        span_length (float): Length of a single catenary span (m).
        n_spans (int): Total number of spans in the model.
        elements_per_span (int): Number of finite elements per span.
        contact_mass_per_m (float): Mass per unit length of the contact wire (kg/m).
        contact_tension (float): Applied mechanical tension in the contact wire (N).
        contact_bending_stiffness (float): Bending stiffness of the contact wire (Nm^2).
        messenger_mass_per_m (float): Mass per unit length of the messenger wire (kg/m).
        messenger_tension (float): Applied mechanical tension in the messenger wire (N).
        messenger_bending_stiffness (float): Bending stiffness of the messenger wire (Nm^2).
        steady_arm_stiffness (float): Vertical stiffness of the steady arms (N/m).
        messenger_support_stiffness (float): Vertical stiffness of the messenger wire supports (N/m).
        dropper_stiffness (float): Axial stiffness of the droppers (N/m).
        dropper_positions (tuple[float, ...]): Longitudinal positions of droppers within a span (m).
        damping_ratio (float): Rayleigh damping ratio for the wire structure.
        contact_stiffness (float): Assumed penalty stiffness for pantograph-wire contact (N/m).
        contact_damping (float): Assumed penalty damping for pantograph-wire contact (Ns/m).
        maximum_presag (float): Maximum mid-span presag allowed in the contact wire (m).
        dropper_preload (float): Assumed static preload in the droppers to ensure tension (N).
        end_anchor_stiffness (float): Vertical stiffness applied at the boundary anchors (N/m).
    """
    # Published simple-catenary reference values.
    span_length: float = 60.0
    n_spans: int = 10
    elements_per_span: int = 12
    contact_mass_per_m: float = 1.35
    contact_tension: float = 20_000.0
    contact_bending_stiffness: float = 195.0
    messenger_mass_per_m: float = 1.07
    messenger_tension: float = 16_000.0
    messenger_bending_stiffness: float = 131.7
    steady_arm_stiffness: float = 300.0
    messenger_support_stiffness: float = 50_000.0
    dropper_stiffness: float = 100_000.0
    dropper_positions: tuple[float, ...] = field(
        default=(5.0, 10.5, 17.0, 23.5, 30.0, 36.5, 43.0, 49.5, 55.0)
    )
    damping_ratio: float = 0.005

    # Explicit assumptions: numerical/contact choices, not claimed reference data.
    contact_stiffness: float = 50_000.0
    contact_damping: float = 80.0
    maximum_presag: float = 0.055
    dropper_preload: float = 90.0
    end_anchor_stiffness: float = 1.0e7

    def __post_init__(self) -> None:
        """Validates the initialized parameters.

        Raises:
            ValueError: If any physical dimensions, masses, tensions, or stiffnesses
                are non-positive, or if dropper positions do not lie strictly within
                a single span.
        """
        positive = (
            self.span_length,
            self.n_spans,
            self.elements_per_span,
            self.contact_mass_per_m,
            self.contact_tension,
            self.messenger_mass_per_m,
            self.messenger_tension,
            self.dropper_stiffness,
            self.contact_stiffness,
            self.end_anchor_stiffness,
        )
        if any(value <= 0 for value in positive):
            raise ValueError("catenary dimensions, masses, tensions, and stiffnesses must be positive")
        if not all(0.0 < x < self.span_length for x in self.dropper_positions):
            raise ValueError("dropper positions must lie strictly inside one span")

    @property
    def dx(self) -> float:
        """Calculates the length of a single finite element.

        Returns:
            float: The element length in meters.
        """
        return self.span_length / self.elements_per_span

    @property
    def n_nodes(self) -> int:
        """Calculates the total number of nodes in the continuous wire model.

        Returns:
            int: The total number of nodes.
        """
        return self.n_spans * self.elements_per_span + 1

    @property
    def length(self) -> float:
        """Calculates the total longitudinal length of the catenary model.

        Returns:
            float: The total length in meters.
        """
        return self.n_spans * self.span_length


PARAMETER_PROVENANCE = {
    "span_length": "published-reference",
    "n_spans": "assumed-numerical-domain",
    "elements_per_span": "assumed-numerical-resolution",
    "contact_mass_per_m": "published-reference",
    "contact_tension": "published-reference",
    "contact_bending_stiffness": "published-reference",
    "messenger_mass_per_m": "published-reference",
    "messenger_tension": "published-reference",
    "messenger_bending_stiffness": "published-reference",
    "steady_arm_stiffness": "published-reference",
    "messenger_support_stiffness": "published-reference",
    "dropper_stiffness": "published-reference",
    "dropper_positions": "published-reference",
    "damping_ratio": "published-reference",
    "contact_stiffness": "assumed-numerical",
    "contact_damping": "assumed-numerical",
    "maximum_presag": "published-reference-standard-preview",
    "dropper_preload": "assumed-equilibrium-linearisation",
    "end_anchor_stiffness": "assumed-boundary",
}
