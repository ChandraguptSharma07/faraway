"""Run PASSIVE vs AeroPINN on the SAME disturbance and compare headline metrics.

Headline metrics: contact-force standard deviation and % time in contact loss
(arcing), passive vs AeroPINN.

Run:  python -m backend.controller.compare
"""

from __future__ import annotations

import numpy as np

from backend.controller.actuator import ForceActuator
from backend.controller.actuator_mpc import ActuatorAwarePINNMPC
from backend.pinn.predict import PINNPredictor
from backend.sim.disturbance import Disturbance
from backend.sim.parameters import BeyondEnvelope, CatenaryParams, PantographParams, kmh_to_ms
from backend.sim.solver import metrics, simulate


def run_comparison(
    speed_kmh: float,
    beyond: BeyondEnvelope | None = None,
    duration: float = 6.0,
    seed: int = 999,
    predictor: PINNPredictor | None = None,
    dt: float = 1.0e-3,
    disturbance_factory=Disturbance,
):
    """Runs a parallel simulation comparing a passive pantograph to an AeroPINN-controlled one.

    Both simulations are subjected to identical disturbance profiles to allow for a direct
    performance comparison based on contact force standard deviation and arcing duration.

    Args:
        speed_kmh (float): The simulated train speed in kilometers per hour.
        beyond (BeyondEnvelope | None, optional): Environmental and simulation boundary extensions.
        duration (float, optional): The duration of the simulation in seconds. Defaults to 6.0.
        seed (int, optional): Random seed used for generating the disturbance profile. Defaults to 999.
        predictor (PINNPredictor | None, optional): The PINN model to use for the active controller.
        dt (float, optional): Simulation time step in seconds. Defaults to 1.0e-3.
        disturbance_factory (callable, optional): Factory function for creating disturbance objects. Defaults to Disturbance.

    Returns:
        dict: A dictionary containing comparison metrics, the simulation configurations,
            and raw simulation results for both the passive and aeropinn runs.
    """
    beyond = beyond or BeyondEnvelope()
    predictor = predictor or PINNPredictor()
    cat = CatenaryParams()
    panto = PantographParams()
    speed_ms = kmh_to_ms(speed_kmh)

    # identical disturbance for both systems
    dist_p = disturbance_factory(cat, seed=seed)
    dist_a = disturbance_factory(cat, seed=seed)

    passive = simulate(
        speed_ms,
        duration=duration,
        dt=dt,
        cat=cat,
        panto=panto,
        beyond=beyond,
        dist=dist_p,
    )

    actuator = ForceActuator(dt)
    controller = ActuatorAwarePINNMPC(
        predictor,
        actuator,
        dist_a,
        speed_ms,
        beyond,
    )

    def applied_force(t, state, force):
        """Wrapper to apply the PINN-MPC command to the force actuator.

        Args:
            t (float): Current simulation time in seconds.
            state: Current pantograph state vector.
            force (float): Currently measured contact force in Newtons.

        Returns:
            float: The applied actuator force for this timestep in Newtons.
        """
        return actuator.step(controller(t, state, force))

    aeropinn = simulate(
        speed_ms,
        duration=duration,
        dt=dt,
        cat=cat,
        panto=panto,
        beyond=beyond,
        dist=dist_a,
        f_control_fn=applied_force,
    )

    mp, ma = metrics(passive), metrics(aeropinn)
    return {
        "mode": "REDUCED_TRUTH_STATE_DIAGNOSTIC",
        "speed_kmh": speed_kmh,
        "passive": mp,
        "aeropinn": ma,
        "passive_res": passive,
        "aeropinn_res": aeropinn,
    }


def run_live_comparison(
    speed_kmh: float,
    beyond: BeyondEnvelope | None = None,
    duration: float = 2.0,
    settle_duration: float = 1.0,
    seed: int = 999,
    predictor: PINNPredictor | None = None,
):
    """Exercise the same coupled, estimated-state controller used by the server.

    Runs the deployed Engine configuration which includes the full sensor estimation
    loop, unlike the idealized state feedback used in run_comparison.

    Args:
        speed_kmh (float): The simulated train speed in kilometers per hour.
        beyond (BeyondEnvelope | None, optional): Environmental and simulation boundary extensions.
        duration (float, optional): The duration of the scored simulation interval in seconds. Defaults to 2.0.
        settle_duration (float, optional): Initial unscored stabilization period in seconds. Defaults to 1.0.
        seed (int, optional): Random seed used for disturbance generation. Defaults to 999.
        predictor (PINNPredictor | None, optional): The PINN model to use for prediction.

    Returns:
        dict: A dictionary containing force tracking and timing metrics for the live controller.
    """
    from backend.server.engine import Engine

    beyond = beyond or BeyondEnvelope()
    engine = Engine(seed=seed, predictor=predictor or PINNPredictor())
    engine.set_speed(speed_kmh)
    engine.set_tension(beyond.tension_factor)
    engine.set_turbulence(beyond.turbulence_gain)
    engine.step(int(round(settle_duration / engine.dt)))
    if beyond.gust:
        # Keep startup equilibration out of the scored window, but preserve the
        # requested transient in the actual comparison interval.
        engine.trigger_gust(beyond.gust)

    count = int(round(duration / engine.dt))
    passive = np.empty(count)
    active = np.empty(count)
    for index in range(count):
        engine.step()
        passive[index] = engine.force_p
        active[index] = engine.force_a

    def force_metrics(values):
        """Computes statistical metrics from an array of contact forces.

        Args:
            values (np.ndarray): An array of contact forces in Newtons.

        Returns:
            dict: A dictionary containing mean, standard deviation, and percentage of contact loss.
        """
        return {
            "mean_N": float(np.mean(values)),
            "std_N": float(np.std(values)),
            "loss_of_contact_pct": 100.0 * float(np.mean(values <= 0.0)),
        }

    return {
        "mode": "DEPLOYED_SIMULATION_PATH",
        "speed_kmh": speed_kmh,
        "passive": force_metrics(passive),
        "aeropinn": force_metrics(active),
        "control": {
            "period_ms": 1.0e3 * engine.controller.control_period,
            "authority_N": engine.controller.command_limit,
            "state_input": "SENSOR_EKF_ESTIMATE",
            "actuator_in_loop": True,
        },
        "timing": engine.controller.timing_metrics(),
    }


def _fmt(m):
    """Formats contact force metrics into a human-readable string.

    Args:
        m (dict): A dictionary of metrics containing 'mean_N', 'std_N', and 'loss_of_contact_pct'.

    Returns:
        str: A formatted string summarizing the provided metrics.
    """
    return f"mean={m['mean_N']:6.1f}  std={m['std_N']:6.2f}  loss={m['loss_of_contact_pct']:5.2f}%"


if __name__ == "__main__":
    pred = PINNPredictor()
    print("PINN latency:", {k: round(v, 4) if isinstance(v, float) else v
                            for k, v in pred.benchmark_latency().items()})
    scenarios = [
        ("validated 300 (no arcing)", 300, BeyondEnvelope()),
        ("beyond 340 (passive arcs)", 340, BeyondEnvelope(tension_factor=0.5, turbulence_gain=4.0)),
        ("beyond 350 (passive arcs)", 350, BeyondEnvelope(tension_factor=0.5, turbulence_gain=3.5)),
        ("beyond 360 (extreme)", 360, BeyondEnvelope(tension_factor=0.4, turbulence_gain=4.0)),
    ]
    for name, kmh, b in scenarios:
        out = run_comparison(kmh, beyond=b, predictor=pred)
        print(f"\n[{name}]")
        print("  PASSIVE :", _fmt(out["passive"]))
        print("  AeroPINN:", _fmt(out["aeropinn"]))
        dstd = 100 * (1 - out["aeropinn"]["std_N"] / out["passive"]["std_N"])
        print(f"  -> std reduced {dstd:.0f}%, "
              f"arc {out['passive']['loss_of_contact_pct']:.2f}% -> "
              f"{out['aeropinn']['loss_of_contact_pct']:.2f}%")
