# Changelog

All notable changes to this project will be documented in this file.

## [Unreleased]
### Added
- Added `simulate_live` modal consistency endpoint at `/api/modal-calibration` to compare the live 36-mode catenary vs the implicit distributed reference.
- Added a new `LIVE MODAL MODEL · CROSS-MODEL CONSISTENCY` UI section to `CredibilityView.jsx` in the frontend.

### Changed
- Improved physics engine performance by removing expensive numpy array operations (`np.outer`, `np.ndim`) in `backend/sim/disturbance.py` when evaluating scalar time steps.
- Decoupled Three.js track animation from the backend `current.t` to fix visual stuttering in the frontend.
- Increased shadow simulation duration to 3.0s to allow startup transients to decay in the distributed solver.
- Restored sourced catenary parameters and strict contact-loss agreement gates in shadow comparisons.
- Stabilized MPC candidate selection against sub-resolution numerical cost ties using minimum-effort resolution.

### Fixed
- Fixed an `ImportError` for `libstdc++.so.6` on NixOS by patching `run_local.sh` to inject the correct `LD_LIBRARY_PATH`.
- Fixed a huge `TypeError` bug caused by passing `np.float64` to `type(t) is float` in `backend/sim/disturbance.py`.
- Fixed React rendering lag in `ForceTrace.jsx` by throttling `uPlot` redraws.
- Reduced GPU overhead by dropping Three.js `pixelRatio` to 1.0 and fully discarding hidden train cars in `World3D.jsx`.

- Created `run_local.sh` to run the frontend and backend servers concurrently without Docker.
- Created `Makefile` with an `up` target to run the `run_local.sh` script via `make up`.
