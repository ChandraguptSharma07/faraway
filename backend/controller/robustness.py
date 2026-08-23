"""Promotion gates for actuator-aware control experiments.

This is simulation evidence, not hardware certification. A candidate configuration
must improve the passive plant, retain contact, respect timing, and avoid implausible
mean-force shifts before it can be presented as actuator-in-loop capable.
"""

from __future__ import annotations

from dataclasses import dataclass


ACTUATOR_SWEEP = tuple(
    (response_hz, delay_ms)
    for response_hz in (3.0, 7.0, 10.0)
    for delay_ms in (2.0, 8.0, 15.0)
)

OPERATING_SCENARIOS = {
    "nominal_300": {
        "speed_kmh": 300.0,
        "tension_factor": 1.0,
        "turbulence_gain": 1.0,
    },
    "harsh_350": {
        "speed_kmh": 350.0,
        "tension_factor": 0.5,
        "turbulence_gain": 3.5,
    },
}


@dataclass(frozen=True)
class PromotionThresholds:
    """Thresholds for promoting a candidate controller configuration.

    Attributes:
        max_arc_pct: Maximum allowed percentage of contact loss (arcing).
        max_deadline_miss_pct: Maximum allowed percentage of missed real-time deadlines.
        mean_force_low_N: Minimum acceptable mean contact force in Newtons.
        mean_force_high_N: Maximum acceptable mean contact force in Newtons.
    """
    max_arc_pct: float = 1.0
    max_deadline_miss_pct: float = 1.0
    mean_force_low_N: float = 90.0
    mean_force_high_N: float = 130.0


def evaluate_promotion(
    passive: dict,
    controlled: dict,
    timing: dict,
    thresholds: PromotionThresholds | None = None,
) -> dict:
    """Evaluate whether a controlled simulation meets the criteria for promotion.

    Return individual gates; never collapse failed evidence into "validated".

    Args:
        passive: Metrics from the passive plant simulation.
        controlled: Metrics from the controlled plant simulation.
        timing: Controller timing metrics.
        thresholds: Optional custom thresholds for promotion evaluation. Defaults to standard PromotionThresholds.

    Returns:
        A dictionary containing the promotion status, detailed gate evaluations, and scope.
    """
    limits = thresholds or PromotionThresholds()
    gates = [
        {
            "name": "force variation improves",
            "pass": controlled["std_N"] < passive["std_N"],
            "value": controlled["std_N"],
            "limit": passive["std_N"],
            "unit": "N",
        },
        {
            "name": "contact loss bounded",
            "pass": controlled["loss_of_contact_pct"] <= limits.max_arc_pct,
            "value": controlled["loss_of_contact_pct"],
            "limit": limits.max_arc_pct,
            "unit": "%",
        },
        {
            "name": "mean force plausible",
            "pass": limits.mean_force_low_N <= controlled["mean_N"] <= limits.mean_force_high_N,
            "value": controlled["mean_N"],
            "limit": [limits.mean_force_low_N, limits.mean_force_high_N],
            "unit": "N",
        },
        {
            "name": "real-time deadline",
            "pass": timing["deadline_miss_pct"] <= limits.max_deadline_miss_pct,
            "value": timing["deadline_miss_pct"],
            "limit": limits.max_deadline_miss_pct,
            "unit": "%",
        },
    ]
    return {
        "status": "PROMOTION_READY" if all(g["pass"] for g in gates) else "INVESTIGATE",
        "gates": gates,
        "scope": "simulation-only",
    }


def run_uncertainty_sweep(duration: float = 6.0, seed: int = 999) -> list[dict]:
    """Execute a sweep of simulations across various actuator parameters and operating scenarios.

    Reproduce the 3–10 Hz / 2–15 ms actuator robustness experiment. Evaluates the
    controller against different operational scenarios and actuator characteristics.

    Args:
        duration: The total duration of each simulation in seconds.
        seed: Random seed for disturbance generation.

    Returns:
        A list of dictionaries, each containing metrics and promotion results for a specific scenario and actuator configuration.
    """
    from backend.controller.actuator import ActuatorParams, ForceActuator
    from backend.controller.actuator_mpc import (
        DEPLOYED_CANDIDATES,
        DEPLOYED_COMMAND_LIMIT,
        DEPLOYED_CONTROL_PERIOD,
        DEPLOYED_ROLLOUT_STEPS,
        ActuatorAwarePINNMPC,
    )
    from backend.pinn.predict import PINNPredictor
    from backend.sim.disturbance import Disturbance
    from backend.sim.parameters import (
        BeyondEnvelope,
        CatenaryParams,
        kmh_to_ms,
    )
    from backend.sim.solver import metrics, simulate

    predictor = PINNPredictor()
    rows = []
    for scenario_name, scenario in OPERATING_SCENARIOS.items():
        speed_kmh = scenario["speed_kmh"]
        speed_ms = kmh_to_ms(speed_kmh)
        beyond = BeyondEnvelope(
            tension_factor=scenario["tension_factor"],
            turbulence_gain=scenario["turbulence_gain"],
        )
        passive = metrics(simulate(
            speed_ms,
            duration=duration,
            beyond=beyond,
            dist=Disturbance(CatenaryParams(), seed=seed),
        ))
        for response_hz, delay_ms in ACTUATOR_SWEEP:
            dist = Disturbance(CatenaryParams(), seed=seed)
            actuator = ForceActuator(
                1.0e-3,
                ActuatorParams(
                    response_time=1.0 / (2.0 * 3.141592653589793 * response_hz),
                    transport_delay=delay_ms * 1.0e-3,
                ),
            )
            controller = ActuatorAwarePINNMPC(
                predictor,
                actuator,
                dist,
                speed_ms,
                beyond,
                n_candidates=DEPLOYED_CANDIDATES,
                rollout_steps=DEPLOYED_ROLLOUT_STEPS,
                control_period=DEPLOYED_CONTROL_PERIOD,
                w_rate=1.5e-3,
                command_limit=DEPLOYED_COMMAND_LIMIT,
            )

            def applied_force(t, state, force):
                """Calculate the applied force from the actuator for the given time and state.

                Args:
                    t: Current simulation time in seconds.
                    state: Current state vector of the system.
                    force: The desired force command.

                Returns:
                    The actual force applied by the actuator after stepping.
                """
                return actuator.step(controller(t, state, force))

            controlled = metrics(simulate(
                speed_ms,
                duration=duration,
                beyond=beyond,
                dist=dist,
                f_control_fn=applied_force,
            ))
            timing = controller.timing_metrics()
            rows.append({
                "scenario": scenario_name,
                "response_hz": response_hz,
                "delay_ms": delay_ms,
                "passive": passive,
                "controlled": controlled,
                "timing": timing,
                "promotion": evaluate_promotion(passive, controlled, timing),
            })
    return rows


if __name__ == "__main__":
    for row in run_uncertainty_sweep():
        controlled = row["controlled"]
        print(
            f'{row["scenario"]:<12} {row["response_hz"]:>4.1f} Hz '
            f'{row["delay_ms"]:>4.0f} ms  {row["promotion"]["status"]:<15} '
            f'std={controlled["std_N"]:6.1f} N  '
            f'arc={controlled["loss_of_contact_pct"]:5.1f}%'
        )
