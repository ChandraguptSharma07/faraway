# Changelog

All notable changes to this project will be documented in this file.

## [Unreleased]
### Added
- Added automatic persistent journey logging with route/GPS documentation, event indexing, accessible session management, and CSV/JSON/ZIP audit exports.
- Added a reproducible Lastochka high-wind sample journey generated through the production simulation path.
- Added `simulate_live` modal consistency endpoint at `/api/modal-calibration` to compare the live 36-mode catenary vs the implicit distributed reference.
- Added a new `LIVE MODAL MODEL · CROSS-MODEL CONSISTENCY` UI section to `CredibilityView.jsx` in the frontend.

### Changed
- Improved physics engine performance by removing expensive numpy array operations (`np.outer`, `np.ndim`) in `backend/sim/disturbance.py` when evaluating scalar time steps.
- Decoupled Three.js track animation from the backend `current.t` to fix visual stuttering in the frontend.
- Increased shadow simulation duration to 3.0s to allow startup transients to decay in the distributed solver.
- Restored sourced catenary parameters and strict contact-loss agreement gates in shadow comparisons.
- Stabilized MPC candidate selection against sub-resolution numerical cost ties using minimum-effort resolution.
- Aligned controller evidence with the deployed 25 N, 18 ms, sensor/EKF and actuator-in-loop configuration.
- Removed the distributed solver's artificial aerodynamic startup load step, separated incompatible uplift definitions, and added quantitative 36/48-mode convergence gates.
- Integrated track travel across speed changes, added pixel-budgeted rendering, deferred the validation bundle, and removed the machine-specific Nix library path.
- Added a machine-readable physical-calibration boundary and measured-data contract; relabelled EN 50318 results as reference checks.

### Fixed
- Fixed an `ImportError` for `libstdc++.so.6` on NixOS by patching `run_local.sh` to inject the correct `LD_LIBRARY_PATH`.
- Optimized scalar-time handling for NumPy ODE inputs in `backend/sim/disturbance.py`.
- Fixed React rendering lag in `ForceTrace.jsx` by throttling `uPlot` redraws.
- Reduced GPU overhead with a pixel-budgeted Three.js render ratio and by fully discarding hidden train cars in `World3D.jsx`.

- Created `run_local.sh` to run the frontend and backend servers concurrently without Docker.
- Created `Makefile` with an `up` target to run the `run_local.sh` script via `make up`.
