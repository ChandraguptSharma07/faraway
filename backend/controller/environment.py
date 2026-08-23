"""Environment prior available to onboard estimation and prediction.

Unlike the simulated plant disturbance, this prior contains no random turbulence or
future gust knowledge. Span geometry, tension setting, speed and the nominal v² aero
law are treated as available onboard configuration/telemetry.
"""

from __future__ import annotations

import numpy as np

from backend.sim.parameters import BeyondEnvelope, CatenaryParams


class CatenaryPrior:
    """Prior knowledge of the catenary environment available to the controller.

    This class provides the controller with estimates of the wire height
    and aerodynamic forces, assuming nominal parameters without random
    turbulence or precise future gust knowledge.
    """
    def __init__(self, cat: CatenaryParams):
        """Initializes the CatenaryPrior with catenary parameters.

        Args:
            cat (CatenaryParams): The nominal catenary parameters.
        """
        self.cat = cat

    def y_wire(self, t, speed_ms: float, beyond: BeyondEnvelope):
        """Calculates the estimated wire height at a given time or times.

        Args:
            t (float or np.ndarray): The current time(s) in seconds.
            speed_ms (float): The train speed in meters per second.
            beyond (BeyondEnvelope): Beyond-envelope parameters including tension factor.

        Returns:
            float or np.ndarray: The estimated wire height.
        """
        x = speed_ms * np.asarray(t)
        tension = max(beyond.tension_factor, 1.0e-3)
        return (
            self.cat.a_span / tension * np.cos(2.0 * np.pi * x / self.cat.span_length)
            + self.cat.a_span2 / tension
            * np.cos(4.0 * np.pi * x / self.cat.span_length)
        )

    def aero_force(self, speed_ms: float, _beyond: BeyondEnvelope) -> float:
        """Calculates the estimated aerodynamic force on the pantograph.

        Args:
            speed_ms (float): The train speed in meters per second.
            _beyond (BeyondEnvelope): Unused beyond-envelope parameters.

        Returns:
            float: The estimated aerodynamic force in Newtons.
        """
        return self.cat.c_aero * speed_ms * speed_ms
