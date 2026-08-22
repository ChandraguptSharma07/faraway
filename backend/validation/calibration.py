"""Machine-readable claim boundary and real-system data requirements."""

from __future__ import annotations


CALIBRATION_STATUS = {
    "status": "REFERENCE_BENCHMARK_ONLY",
    "route_identified": False,
    "hardware_validated": False,
    "controller_certified": False,
    "current_evidence": [
        "EN 50318 numerical reference-range checks at 250 and 300 km/h",
        "cross-model and modal-convergence simulation checks",
        "sensor, estimator, actuator, and controller simulation-in-loop tests",
    ],
    "asset_boundary": {
        "lastochka_glb": "visual geometry only",
        "physical_train": "not identified",
        "physical_pantograph": "not identified",
        "physical_catenary_route": "not identified",
    },
    "required_dataset_groups": [
        "pantograph mechanical and aerodynamic identification",
        "catenary geometry, material, tension, support, and dropper data",
        "actuator command-to-force identification",
        "synchronized run telemetry with force, motion, speed, and position",
        "weather and wire-temperature measurements",
        "independent blind-validation runs",
    ],
    "next_gate": "INGEST_MEASURED_BASELINE_DATA",
    "contract": "docs/REAL_SYSTEM_CALIBRATION.md",
}


def calibration_status() -> dict:
    """Return a copy safe for API consumers to annotate."""
    return {
        **CALIBRATION_STATUS,
        "current_evidence": list(CALIBRATION_STATUS["current_evidence"]),
        "asset_boundary": dict(CALIBRATION_STATUS["asset_boundary"]),
        "required_dataset_groups": list(
            CALIBRATION_STATUS["required_dataset_groups"]
        ),
    }
