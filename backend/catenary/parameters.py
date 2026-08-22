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
        return self.span_length / self.elements_per_span

    @property
    def n_nodes(self) -> int:
        return self.n_spans * self.elements_per_span + 1

    @property
    def length(self) -> float:
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
