import re

with open('backend/validation/shadow.py', 'r') as f:
    content = f.read()

new_func = """
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
    speed_ms = kmh_to_ms(speed_kmh)
    fine_params = replace(
        DistributedCatenaryParams(),
        n_spans=config.n_spans,
        elements_per_span=config.fine_elements_per_span,
    )
    cat = replace(CatenaryParams(), turb_std=0.0)
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

"""

content = content.replace("def run_shadow_scenario", new_func + "def run_shadow_scenario")
with open('backend/validation/shadow.py', 'w') as f:
    f.write(content)
