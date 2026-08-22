"""Environment prior available to onboard estimation and prediction.

Unlike the simulated plant disturbance, this prior contains no random turbulence or
future gust knowledge. Span geometry, tension setting, speed and the nominal v² aero
law are treated as available onboard configuration/telemetry.
"""

from __future__ import annotations

import numpy as np

from backend.sim.parameters import BeyondEnvelope, CatenaryParams


class CatenaryPrior:
    def __init__(self, cat: CatenaryParams):
        self.cat = cat

    def y_wire(self, t, speed_ms: float, beyond: BeyondEnvelope):
        x = speed_ms * np.asarray(t)
        tension = max(beyond.tension_factor, 1.0e-3)
        return (
            self.cat.a_span / tension * np.cos(2.0 * np.pi * x / self.cat.span_length)
            + self.cat.a_span2 / tension
            * np.cos(4.0 * np.pi * x / self.cat.span_length)
        )

    def aero_force(self, speed_ms: float, _beyond: BeyondEnvelope) -> float:
        return self.cat.c_aero * speed_ms * speed_ms
