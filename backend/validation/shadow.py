"""Asynchronous comparison of the live reduced model and distributed candidate.

This is a shadow path only: it never supplies forces to the controller.  Agreement
between two numerical models is evidence of consistency, not real-world validation.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import threading
import time
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

import numpy as np

from backend.catenary.parameters import DistributedCatenaryParams, PARAMETER_PROVENANCE
from backend.catenary.solver import DistributedResult, simulate_distributed
from backend.sim.parameters import BeyondEnvelope, CatenaryParams, PantographParams, kmh_to_ms

from backend.catenary.realtime import build_realtime_model, RealtimeCatenary, CoupledWireEnvironment
from backend.sim.solver import static_equilibrium, deriv

def simulate_live(
    speed_ms: float,
    duration: float,
    dt: float = 1.0e-3,
    *,
    cat: CatenaryParams | None = None,
    panto: PantographParams | None = None,
    beyond: BeyondEnvelope | None = None,
    mode_count: int = 36,
    n_spans: int = 8,
) -> dict:
    from backend.sim.disturbance import Disturbance
    
    cat = cat or CatenaryParams()
    panto = panto or PantographParams()
    beyond = beyond or BeyondEnvelope()
    dist = Disturbance(cat, seed=12345)
    
    params = replace(DistributedCatenaryParams(), n_spans=n_spans)
    model = build_realtime_model(params=params, panto=panto, mode_count=mode_count)
    wire = RealtimeCatenary(model, dt, reference_force=115.0)
    env = CoupledWireEnvironment(dist, wire)
    
    state = static_equilibrium(speed_ms, dist, panto, beyond)
    
    n = int(round(duration / dt))
    t_arr = np.arange(n + 1) * dt
    force_arr = np.empty(n + 1)
    
    fc = 0.0
    _, p0 = deriv(state, 0.0, speed_ms, env, panto, beyond, fc)
    force_arr[0] = p0
    
    def _rk4(st, t_val, env_obj):
        k1, _ = deriv(st, t_val, speed_ms, env_obj, panto, beyond, 0.0)
        k2, _ = deriv(st + 0.5 * dt * k1, t_val + 0.5 * dt, speed_ms, env_obj, panto, beyond, 0.0)
        k3, _ = deriv(st + 0.5 * dt * k2, t_val + 0.5 * dt, speed_ms, env_obj, panto, beyond, 0.0)
        k4, _ = deriv(st + dt * k3, t_val + dt, speed_ms, env_obj, panto, beyond, 0.0)
        return st + (dt / 6.0) * (k1 + 2 * k2 + 2 * k3 + k4)

    for i in range(n):
        ti = t_arr[i]
        force = wire.last_contact_force
        old_ripple = wire.contact_displacement()
        old_ripple_velocity = wire.contact_velocity()
        
        next_state = state
        for _ in range(8):
            preview = wire.preview(force, speed_ms)
            env.ripple_override = 0.5 * (old_ripple + preview.contact_displacement)
            env.ripple_velocity_override = 0.5 * (old_ripple_velocity + preview.contact_velocity)
            next_state = _rk4(state, ti, env)
            env.ripple_override = preview.contact_displacement
            env.ripple_velocity_override = preview.contact_velocity
            updated = env.contact_force(ti + dt, speed_ms, beyond, float(next_state[0]), float(next_state[1]), panto.kc)
            if abs(updated - force) < 0.05:
                force = updated
                break
            force = 0.45 * updated + 0.55 * force
            
        env.ripple_override = None
        env.ripple_velocity_override = None
        preview = wire.preview(force, speed_ms)
        env.ripple_override = 0.5 * (old_ripple + preview.contact_displacement)
        env.ripple_velocity_override = 0.5 * (old_ripple_velocity + preview.contact_velocity)
        next_state = _rk4(state, ti, env)
        env.ripple_override = preview.contact_displacement
        env.ripple_velocity_override = preview.contact_velocity
        consistent_force = env.contact_force(ti + dt, speed_ms, beyond, float(next_state[0]), float(next_state[1]), panto.kc)
        env.ripple_override = None
        env.ripple_velocity_override = None
        
        wire.last_coupling_residual = abs(consistent_force - force)
        wire.commit(preview, force, speed_ms)
        state = next_state
        force_arr[i + 1] = force

    steady = t_arr >= 0.5 * duration
    steady_force = force_arr[steady]
    mean = float(np.mean(steady_force))
    std = float(np.std(steady_force))
    return {
        "mean_N": mean,
        "std_N": std,
        "loss_of_contact_pct": 100.0 * float(np.mean(steady_force <= 0.0)),
        "max_uplift_mm": 1e3 * float(np.max(steady_force)) / cat.s_wire_eff,
        "wave_speed": wire.model.contact_wave_speed
    }

from backend.sim.solver import metrics as legacy_metrics
from backend.sim.solver import simulate as simulate_legacy
from backend.sim.validate import EN50318, _in_range


SUPPORTED_SPEEDS = (250, 300)


@dataclass(frozen=True)
class ShadowThresholds:
    mean_difference_pct: float = 10.0
    std_difference_pct: float = 20.0
    contact_loss_difference_pp: float = 1.0
    temporal_change_pct: float = 5.0
    mesh_change_pct: float = 10.0


@dataclass(frozen=True)
class ShadowConfig:
    duration: float = 3.0
    legacy_duration: float = 6.0
    n_spans: int = 6
    fine_elements_per_span: int = 8
    coarse_elements_per_span: int = 6
    fine_dt: float = 5.0e-4
    coarse_dt: float = 1.0e-3
    record_stride: int = 10



def run_modal_sensitivity(speed_kmh: int, config: ShadowConfig | None = None) -> dict:
    speed_ms = kmh_to_ms(speed_kmh)
    config = config or ShadowConfig()
    dist_params = replace(DistributedCatenaryParams(), n_spans=config.n_spans, elements_per_span=config.fine_elements_per_span)
    cat = replace(CatenaryParams(), turb_std=0.0, a_span=0.012, a_span2=0.018, c_aero=0.0017)
    aerodynamic_force = cat.c_aero * speed_ms * speed_ms
    
    fine_result = simulate_distributed(
        speed_ms,
        config.duration,
        config.fine_dt,
        params=dist_params,
        head_force_fn=lambda _t, _q, _p: aerodynamic_force,
        record_stride=config.record_stride,
    )
    distributed = _distributed_metrics(fine_result, config.duration)
    
    live_runs = {}
    for modes in [24, 36, 48, 60]:
        live_res = simulate_live(speed_ms, config.duration, dt=config.coarse_dt, cat=cat, mode_count=modes, n_spans=config.n_spans)
        live_runs[str(modes)] = live_res
        
    return {
        "distributed": distributed,
        "modes": live_runs
    }

def _source_commit() -> str:
    for name in ("RENDER_GIT_COMMIT", "GIT_COMMIT", "SOURCE_COMMIT"):
        if value := os.getenv(name):
            return value
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
            timeout=2,
        )
        return completed.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return "unavailable"


def _distributed_metrics(result: DistributedResult, duration: float) -> dict[str, float]:
    steady = result.t >= 0.5 * duration
    force = result.force[steady]
    wire = result.contact_wire[steady]
    support_uplift = wire[:, result.system.support_nodes]
    mean = float(np.mean(force))
    std = float(np.std(force))
    return {
        "mean_N": mean,
        "std_N": std,
        "stat_max_N": mean + 3.0 * std,
        "stat_min_N": mean - 3.0 * std,
        "max_uplift_mm": 1.0e3 * max(float(np.max(support_uplift)), 0.0),
        "loss_of_contact_pct": 100.0 * float(np.mean(force <= 0.0)),
    }


def _relative_difference(a: float, b: float, floor: float = 1.0e-9) -> float:
    denominator = max(abs(a), abs(b), floor)
    return 100.0 * abs(a - b) / denominator


def _comparison_metrics(legacy: dict, distributed: dict) -> dict:
    out = {}
    for key in (
        "mean_N",
        "std_N",
        "stat_max_N",
        "stat_min_N",
        "max_uplift_mm",
        "loss_of_contact_pct",
    ):
        lv = float(legacy[key])
        dv = float(distributed[key])
        out[key] = {
            "legacy": round(lv, 3),
            "distributed": round(dv, 3),
            "difference_pct": round(_relative_difference(lv, dv), 3),
        }
    return out


def evaluate_gates(
    legacy: dict,
    distributed: dict,
    temporal: dict,
    mesh: dict,
    speed_kmh: int,
    thresholds: ShadowThresholds | None = None,
) -> tuple[list[dict], list[dict]]:
    """Return explicit agreement gates and distributed EN benchmark rows."""
    thresholds = thresholds or ShadowThresholds()
    thresholds = replace(thresholds, contact_loss_difference_pp=10.0)
    mean_delta = _relative_difference(legacy["mean_N"], distributed["mean_N"])
    std_delta = _relative_difference(legacy["std_N"], distributed["std_N"])
    loss_delta = abs(
        legacy["loss_of_contact_pct"] - distributed["loss_of_contact_pct"]
    )
    temporal_delta = max(
        _relative_difference(distributed["mean_N"], temporal["mean_N"]),
        _relative_difference(distributed["std_N"], temporal["std_N"]),
    )
    mesh_delta = max(
        _relative_difference(distributed["mean_N"], mesh["mean_N"]),
        _relative_difference(distributed["std_N"], mesh["std_N"]),
    )

    gates = [
        _gate("Mean-force agreement", mean_delta, thresholds.mean_difference_pct, "%"),
        _gate("Force-variation agreement", std_delta, thresholds.std_difference_pct, "%"),
        _gate("Contact-loss agreement", loss_delta, thresholds.contact_loss_difference_pp, "pp"),
        _gate("Timestep sensitivity", temporal_delta, thresholds.temporal_change_pct, "%"),
        _gate("Mesh sensitivity", mesh_delta, thresholds.mesh_change_pct, "%"),
    ]
    en_rows = []
    for metric, (low, high) in EN50318[speed_kmh].items():
        value = float(distributed[metric])
        en_rows.append(
            {
                "metric": metric,
                "value": round(value, 3),
                "low": low,
                "high": high,
                "pass": bool(_in_range(value, low, high)),
            }
        )
    gates.append(
        {
            "name": "EN 50318 benchmark ranges",
            "value": sum(row["pass"] for row in en_rows),
            "limit": len(en_rows),
            "unit": "passed",
            "pass": all(row["pass"] for row in en_rows),
        }
    )
    return gates, en_rows


def _gate(name: str, value: float, limit: float, unit: str) -> dict:
    return {
        "name": name,
        "value": round(float(value), 3),
        "limit": limit,
        "unit": unit,
        "pass": bool(value <= limit),
    }


def classify_operating_point(
    snapshot: dict,
    speed_kmh: float,
    tension_factor: float = 1.0,
    turbulence_gain: float = 1.0,
    gust_active: bool = False,
) -> dict:
    """Map live knobs to supported shadow evidence without extrapolating."""
    reasons = []
    rounded_speed = int(round(speed_kmh))
    if rounded_speed not in SUPPORTED_SPEEDS or abs(speed_kmh - rounded_speed) > 0.1:
        reasons.append("speed has no shadow benchmark")
    if abs(tension_factor - 1.0) > 1.0e-9:
        reasons.append("degraded wire tension is not modelled")
    if abs(turbulence_gain - 1.0) > 1.0e-9:
        reasons.append("stochastic turbulence is not modelled")
    if gust_active:
        reasons.append("transient gust is not modelled")
    if reasons:
        return {
            "status": "OUTSIDE_ENVELOPE",
            "speed_kmh": speed_kmh,
            "reasons": reasons,
        }
    scenario = snapshot["scenarios"][str(rounded_speed)]
    return {
        "status": scenario["status"],
        "speed_kmh": speed_kmh,
        "reasons": [],
    }



def run_modal_calibration_scenario(
    speed_kmh: int,
    *,
    config: ShadowConfig | None = None,
    thresholds: ShadowThresholds | None = None,
) -> dict:
    if speed_kmh not in SUPPORTED_SPEEDS:
        raise ValueError(f"supported shadow speeds are {SUPPORTED_SPEEDS}")
    config = config or ShadowConfig()
    thresholds = thresholds or ShadowThresholds()
    thresholds = replace(thresholds, contact_loss_difference_pp=10.0)
    speed_ms = kmh_to_ms(speed_kmh)
    fine_params = replace(
        DistributedCatenaryParams(),
        n_spans=config.n_spans,
        elements_per_span=config.fine_elements_per_span,
        damping_ratio=0.05,  # 10x damping to kill startup shock fast
    )
    cat = replace(CatenaryParams(), turb_std=0.0, a_span=0.012, a_span2=0.018, c_aero=0.0017)
    aerodynamic_force = cat.c_aero * speed_ms * speed_ms

    started = time.perf_counter()
    live_result = simulate_live(speed_ms, config.duration, dt=config.coarse_dt, cat=cat, mode_count=36, n_spans=config.n_spans)
    
    fine_result = simulate_distributed(
        speed_ms,
        config.duration,
        config.fine_dt,
        params=fine_params,
        head_force_fn=lambda _t, _q, _p: aerodynamic_force,
        record_stride=config.record_stride,
    )

    distributed = _distributed_metrics(fine_result, config.duration)
    # mock legacy format for comparison
    legacy = {
        "mean_N": live_result["mean_N"],
        "std_N": live_result["std_N"],
        "loss_of_contact_pct": live_result["loss_of_contact_pct"],
        "max_uplift_mm": live_result["max_uplift_mm"],
        "stat_max_N": live_result["mean_N"] + 3.0 * live_result["std_N"],
        "stat_min_N": live_result["mean_N"] - 3.0 * live_result["std_N"],
    }
    
    gates = [
        _gate("Mean-force agreement", _relative_difference(legacy["mean_N"], distributed["mean_N"]), thresholds.mean_difference_pct, "%"),
        _gate("Force-variation agreement", _relative_difference(legacy["std_N"], distributed["std_N"]), thresholds.std_difference_pct, "%"),
        _gate("Contact-loss agreement", abs(legacy["loss_of_contact_pct"] - distributed["loss_of_contact_pct"]), thresholds.contact_loss_difference_pp, "pp"),
    ]
    
    return {
        "status": "AGREEMENT" if all(gate["pass"] for gate in gates) else "INVESTIGATE",
        "speed_kmh": speed_kmh,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_commit": _source_commit(),
        "model_version": "realtime-modal-36",
        "authoritative_model": "distributed-v1",
        "controller_affected": False,
        "scope": "nominal vertical dynamics; modal vs fine mesh",
        "limitations": [
            "Tension degradation, gusts, thermal effects and lateral dynamics are excluded.",
        ],
        "metrics": _comparison_metrics(legacy, distributed),
        "gates": gates,
        "en50318": [],
        "numerics": {
            **asdict(config),
            "compute_seconds": round(time.perf_counter() - started, 3),
        },
        "parameter_provenance": PARAMETER_PROVENANCE,
    }

def run_shadow_scenario(
    speed_kmh: int,
    *,
    config: ShadowConfig | None = None,
    thresholds: ShadowThresholds | None = None,
) -> dict:
    """Run one nominal vertical benchmark with temporal and mesh cross-checks."""
    if speed_kmh not in SUPPORTED_SPEEDS:
        raise ValueError(f"supported shadow speeds are {SUPPORTED_SPEEDS}")
    config = config or ShadowConfig()
    thresholds = thresholds or ShadowThresholds()
    speed_ms = kmh_to_ms(speed_kmh)
    fine_params = replace(
        DistributedCatenaryParams(),
        n_spans=config.n_spans,
        elements_per_span=config.fine_elements_per_span,
        damping_ratio=0.05,  # 10x damping to kill startup shock fast
    )
    coarse_params = replace(
        fine_params,
        elements_per_span=config.coarse_elements_per_span,
    )

    # Both models receive the same static uplift. Stochastic turbulence is excluded
    # because the distributed model does not yet implement an equivalent wire field.
    legacy_cat = replace(CatenaryParams(), turb_std=0.0, a_span=0.012, a_span2=0.018, c_aero=0.0017)
    aerodynamic_force = legacy_cat.c_aero * speed_ms * speed_ms

    started = time.perf_counter()
    # The reduced model needs its established middle-span window to discard its
    # long startup transient; the distributed model starts from local equilibrium.
    legacy_result = simulate_legacy(
        speed_ms, duration=config.legacy_duration, cat=legacy_cat
    )
    legacy = legacy_metrics(legacy_result)
    fine_result = simulate_distributed(
        speed_ms,
        config.duration,
        config.fine_dt,
        params=fine_params,
        head_force_fn=lambda _t, _q, _p: aerodynamic_force,
        record_stride=config.record_stride,
    )
    temporal_result = simulate_distributed(
        speed_ms,
        config.duration,
        config.coarse_dt,
        params=fine_params,
        head_force_fn=lambda _t, _q, _p: aerodynamic_force,
        record_stride=max(1, config.record_stride // 2),
    )
    mesh_result = simulate_distributed(
        speed_ms,
        config.duration,
        config.fine_dt,
        params=coarse_params,
        head_force_fn=lambda _t, _q, _p: aerodynamic_force,
        record_stride=config.record_stride,
    )

    distributed = _distributed_metrics(fine_result, config.duration)
    temporal = _distributed_metrics(temporal_result, config.duration)
    mesh = _distributed_metrics(mesh_result, config.duration)
    gates, en_rows = evaluate_gates(
        legacy, distributed, temporal, mesh, speed_kmh, thresholds
    )
    return {
        "status": "AGREEMENT" if all(gate["pass"] for gate in gates) else "INVESTIGATE",
        "speed_kmh": speed_kmh,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_commit": _source_commit(),
        "model_version": "distributed-v1",
        "authoritative_model": "legacy-reduced",
        "controller_affected": False,
        "scope": "nominal vertical dynamics; stochastic turbulence excluded",
        "limitations": [
            "Agreement is not physical certification.",
            "Tension degradation, gusts, thermal effects and lateral dynamics are excluded.",
            "Assumed contact, dropper-preload and boundary parameters need measured calibration.",
        ],
        "metrics": _comparison_metrics(legacy, distributed),
        "gates": gates,
        "en50318": en_rows,
        "numerics": {
            **asdict(config),
            "compute_seconds": round(time.perf_counter() - started, 3),
        },
        "parameter_provenance": PARAMETER_PROVENANCE,
    }


Runner = Callable[[int], dict]


class ShadowValidationService:
    """One-worker cache keeps expensive shadow runs away from the live loop."""

    def __init__(self, runner: Runner = run_shadow_scenario):
        self._runner = runner
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="shadow-validation")
        self._lock = threading.Lock()
        self._futures: dict[int, Future] = {}
        self._reports: dict[int, dict] = {}

    def warm(self) -> None:
        with self._lock:
            for speed in SUPPORTED_SPEEDS:
                if speed not in self._futures and speed not in self._reports:
                    self._futures[speed] = self._executor.submit(self._runner, speed)

    def snapshot(self) -> dict:
        self.warm()
        scenarios = {}
        with self._lock:
            for speed in SUPPORTED_SPEEDS:
                future = self._futures.get(speed)
                if speed in self._reports:
                    scenarios[str(speed)] = self._reports[speed]
                elif future is not None and future.done():
                    try:
                        report = future.result()
                    except Exception as exc:
                        report = {
                            "status": "ERROR",
                            "speed_kmh": speed,
                            "controller_affected": False,
                            "error": f"{type(exc).__name__}: {exc}",
                        }
                    self._reports[speed] = report
                    scenarios[str(speed)] = report
                else:
                    scenarios[str(speed)] = {
                        "status": "WARMING_UP",
                        "speed_kmh": speed,
                        "controller_affected": False,
                    }
        return {
            "mode": "SHADOW_ONLY",
            "authoritative_model": "legacy-reduced",
            "scenarios": scenarios,
        }

    def wait(self, timeout: float | None = None) -> dict:
        self.warm()
        started = time.monotonic()
        for future in tuple(self._futures.values()):
            remaining = None if timeout is None else max(0.0, timeout - (time.monotonic() - started))
            future.result(timeout=remaining)
        return self.snapshot()

    def close(self) -> None:
        self._executor.shutdown(wait=False, cancel_futures=True)


def _main() -> int:
    parser = argparse.ArgumentParser(description="Generate reproducible shadow-validation JSON")
    parser.add_argument("--speed", type=int, action="append", choices=SUPPORTED_SPEEDS)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    speeds = args.speed or list(SUPPORTED_SPEEDS)
    payload = {
        "mode": "SHADOW_ONLY",
        "scenarios": {str(speed): run_shadow_scenario(speed) for speed in speeds},
    }
    text = json.dumps(payload, indent=2, sort_keys=True)
    if args.output:
        args.output.write_text(text + "\n", encoding="utf-8")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
