# Changelog

All notable changes to this project will be documented in this file.

## [Unreleased]
### Added
- Added comprehensive Google-style docstrings to all Python classes and functions in the backend (`catenary`, `controller`, `pinn`, `server`, `sim`, `validation`).
- Added comprehensive JSDoc comments to all React components, hooks, and utility functions in the frontend.
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

### Fixed
- Fixed an issue in `run_local.sh` where stopping `make up` with Ctrl+C would leave zombie `vite` and `uvicorn` processes running in the background. This caused subsequent runs to fail silently and resulted in WebSocket connection errors (`Firefox can't establish a connection`) because the browser was connecting to a zombie frontend server trying to talk to a dead backend.
- Updated `vite.config.js` proxy target for `/ws` to use `http://` for more reliable WebSocket upgrade handling.
