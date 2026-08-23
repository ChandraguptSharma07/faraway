# AeroPINN

> Active pantograph stabilization for high-speed rail, using a Physics-Informed
> Neural Network as a fast plant predictor inside a model-predictive control loop.

AeroPINN is a research simulation and hackathon demonstrator for maintaining stable
contact between a train pantograph and an overhead contact wire. It runs a passive
pantograph and an actively controlled pantograph against the same disturbance, streams
the comparison to an interactive 3D dashboard, and automatically creates a persistent,
exportable audit record for every journey.

The project is deliberately transparent about its claim boundary: it includes EN 50318
numerical reference checks and several cross-model/software validation layers, but it is
not a route-identified digital twin, certified railway controller, or substitute for
measured train and catenary data. See [Validation and claim boundary](#validation-and-claim-boundary).

## Contents

- [Why AeroPINN exists](#why-aeropinn-exists)
- [What the system does](#what-the-system-does)
- [Architecture](#architecture)
- [Physics and control model](#physics-and-control-model)
- [Dashboard guide](#dashboard-guide)
- [Journey logging and accessible exports](#journey-logging-and-accessible-exports)
- [Quick start](#quick-start)
- [Manual installation](#manual-installation)
- [Running and deployment](#running-and-deployment)
- [API reference](#api-reference)
- [Validation and claim boundary](#validation-and-claim-boundary)
- [Configuration](#configuration)
- [Repository guide](#repository-guide)
- [Known limitations](#known-limitations)
- [Troubleshooting](#troubleshooting)
- [3D asset attribution](#3d-asset-attribution)

## Why AeroPINN exists

At high speed, contact-wire geometry, span transitions, aerodynamic uplift, turbulence,
and transient gusts make the pantograph contact force fluctuate. Too little force can
separate the collector from the wire and produce arcing; too much force increases wear
and mechanical stress.

AeroPINN explores a controller that predicts the near-future contact force and applies
a bounded counter-force to the articulated pantograph frame. The target is a stable
contact force around **115 N**, with lower force variation and less contact loss than a
passive pantograph under the same external forcing.

The PINN is **not a black-box controller**. Its job is narrower:

> Given the estimated pantograph state, local wire motion, aerodynamic force, and a
> candidate actuator force, predict the pantograph response over the next few
> milliseconds.

An explicit model-predictive controller evaluates candidate commands using that
predictor. Sensors, the state estimator, actuator dynamics, safety fallback, catenary
dynamics, and logging remain separate and inspectable.

## What the system does

- Simulates passive and AeroPINN-controlled pantographs at a fixed **1 ms physics step**.
- Couples each lane to its own force-dependent dynamic catenary state while sharing the
  same external disturbance for a fair A/B comparison.
- Represents contact-wire span variation, speed-squared aerodynamic uplift,
  band-limited turbulence, degraded tension, and transient gusts.
- Models sampled, noisy, quantized and delayed sensors feeding a four-state EKF; the
  deployable controller does not read simulator truth directly.
- Models actuator delay, bandwidth, force/rate bounds, and command saturation.
- Streams complete dashboard telemetry at approximately **30 Hz** over WebSocket.
- Shows the train, pantograph articulation, contact wire, force vectors, arcing, live
  force traces, controller timing, and operating condition in an interactive Three.js
  scene.
- Automatically persists native-rate physics, dashboard frames, periodic constants,
  events, journey metadata, and summaries.
- Exports CSV, JSON, or a self-documenting ZIP audit package for offline analysis and
  accessibility tools.
- Provides EN 50318 reference checks, PINN-versus-solver overlays, reduced-versus-
  distributed shadow comparison, and modal convergence evidence.
- Optionally sends the simulated command to an ESP32/Arduino servo as a physical demo
  indicator. Hardware is never required for the software workflow.

## Architecture

```text
 OFFLINE: classical solver ── training targets + ODE residual ──► PINN predictor
                                                                      ▲
                                                                      │ queries
 LIVE: shared disturbance ─┬─► passive plant ◄──────► passive wire    │
                           │                                          │
                           ├─► active plant ◄────────► active wire     │
                           │        │ measurements                     │
                           │        ▼                                  │
                           │   sensors ─► EKF ─► actuator-aware MPC ───┘
                           │                         │ command
                           │                         ▼
                           │                      actuator
                           │                         │ applied force
                           │                         └────► active plant
                           │
                           └─► idealized reference (evidence only)
                                            │
                                            ▼
                        FastAPI + WebSocket + journey recorder
                                  │                    │
                                  ▼                    ▼
                       React/Three.js dashboard   SQLite + NDJSON
                                  │                    │
                                  ▼                    ▼
                         optional USB servo      CSV / JSON / ZIP
```

### Runtime data flow

1. A browser opens `/ws`.
2. The backend creates an independent `Engine` and journey for that WebSocket session.
3. The engine advances 33 native 1 ms steps per streamed frame.
4. Passive and active lanes receive the same exogenous span/turbulence/gust forcing.
5. Their different contact forces produce independent wire ripple states.
6. The active lane crosses a sensor boundary, EKF, controller, and explicit actuator
   before control force reaches the plant.
7. The backend streams the latest frame and logs all native physics samples.
8. Closing the WebSocket finalizes the journey; a process restart marks unfinished
   journeys `INTERRUPTED` rather than discarding them.

## Physics and control model

### Pantograph

The benchmark plant is the EN 50318-style two-mass vertical pantograph model. With
positive displacement upward:

```text
m1 z1'' + r1(z1' - z2') + k1(z1 - z2) = -P + Faero
m2 z2'' + r2 z2' + k2 z2 + r1(z2' - z1') + k1(z2 - z1) = F0 + Fact
P = max(kc(z1 - ywire), 0)
```

- `z1`: collector-head displacement.
- `z2`: articulated-frame displacement.
- `P`: compressive contact force; zero means contact loss.
- `F0`: static uplift.
- `Faero`: aerodynamic uplift and transient gust force.
- `Fact`: active force applied to the articulated frame; zero for the passive lane.

The fixed-step RK4 plant integrator exchanges contact force and wire displacement with
the live catenary through an implicit iteration with a **0.05 N** convergence tolerance
and at most eight coupling iterations.

### Disturbance and environment

The effective wire/environment input contains:

- **Span passing:** support-to-mid-span height variation whose temporal frequency is
  train speed divided by the 60 m span length.
- **Second spatial harmonic:** represents shorter within-span variation.
- **Aerodynamic uplift:** `Faero = c_aero × speed²`.
- **Band-limited turbulence:** deterministic random-phase components up to 8 Hz,
  reproducible from a seed.
- **Wire-tension degradation:** lowers contact and messenger tension and reprojects the
  current wire state into the new modal basis.
- **Gust:** transient force that decays with an approximately 0.18 s time constant.

The simulation currently treats vertical dynamics only. Lateral crosswind,
temperature-dependent material behavior, ice, wear evolution, and train-body motion
are not yet modeled.

### Dynamic catenary

The detailed reference model assembles contact wire, messenger wire, droppers, supports,
tension, bending stiffness, damping, and moving contact. The real-time path reduces
this distributed model to **36 retained modes** and advances them with Newmark
integration inside a moving spatial window.

Each lane owns a separate catenary state. This is important: the controller changes
contact force, contact force changes the outgoing mechanical wave/ripple, and that
changed wire height feeds back into the next contact-force calculation. The active and
passive wires therefore cannot be a single shared animation.

### PINN predictor

`backend/pinn/model.py` defines a small PyTorch network with hard initial-condition
constraints. Its context contains:

```text
[head position, head velocity, frame position, frame velocity,
 aerodynamic force, applied frame force,
 wire position, wire velocity, wire acceleration]
```

The network predicts collector and frame trajectories over a **5 ms horizon**. Contact
force is derived from the physical contact law rather than emitted as an unconstrained
label. Training combines supervised classical-solver targets with residuals from both
pantograph equations of motion. A trained checkpoint is committed at
`backend/pinn/pinn_model.pt` so normal use does not require retraining.

### Sensor, estimator, controller, and actuator chain

The active comparison uses the following explicit chain:

| Stage | Current simulation configuration |
|---|---|
| Sensors | 500 Hz, 2 ms delivery latency, quantization, noise, bias, and seeded dropouts |
| Estimator | Four-state EKF with health checks and stale-data detection |
| Controller | Actuator-aware PINN-MPC, 18 ms period, 21 candidates, 18 × 5 ms rollout steps |
| Command authority | ±25 N in the deployed simulation configuration |
| Actuator model | 4 ms transport delay, 40 ms first-order response, rate and ±98.2 N physical bounds |
| Setpoint | 115 N |

Candidate scoring includes contact-force tracking, effort, command-rate, and wire-wave
terms. Numerically indistinguishable candidates use deterministic minimum-effort
selection. A filtered measured-force bias correction compensates bounded mismatch
between the reduced predictor and the coupled plant.

The controller fails safe to zero active command when the estimator is unhealthy or when
the operating point is outside conservative PINN training support:

- speed above 360 km/h;
- wire-tension factor below 0.5;
- turbulence above 3.5×.

This software fallback is simulation behavior, not an independent railway safety
interlock.

## Dashboard guide

After both servers are running, open `http://localhost:5173`.

### 3D world

- **Drag:** orbit the camera.
- **Mouse wheel:** zoom.
- **Right-drag:** pan.
- **Double-click** or **RESET VIEW:** restore the initial camera.
- **FORCES:** show/hide live static, aerodynamic, control, and contact-force vectors.
- **MOTION ×25 / 1×:** switch between clearly labelled visual amplification and true
  geometric scale. Only the rendering is amplified; HUD values, physics, charts, and
  exported records always remain unscaled.
- The lane cards show live contact force, collector-head displacement in millimetres,
  and contact-held/lost state.
- A red contact point/arc indicates separation.

Real collector motion is only millimetres, so the dashboard starts in labelled 25×
motion mode. The animation amplifies variation around the settled pose rather than
amplifying the static equilibrium deformation.

### Instruments

- **Contact-force trace:** passive and AeroPINN force over the latest rolling window,
  with the 115 N setpoint and zero-force contact-loss threshold.
- **Force σ:** rolling force standard deviation; lower is steadier.
- **Arc time:** percentage of the rolling window at zero contact force.
- **Control P99 / deadline miss:** timing evidence for the active control calculation.
- **EKF / CMD / APPLIED:** estimator health, requested command, and simulated applied
  force.
- **Operating point:** labels non-nominal scenarios rather than presenting them as
  validated conditions.

### Scenario controls

| Control | UI range | Backend clamp | Meaning |
|---|---:|---:|---|
| Speed | 80–400 km/h | 80–400 km/h | Train speed and span-passing frequency |
| Wire tension | 0.30–1.00 | 0.30–1.00 | Fraction of nominal wire tension |
| Turbulence | 0.5–4.0× | 0.5–4.0× | Multiplier on stochastic wire disturbance |
| Gust | 80 N button | supplied value | Decaying transient aerodynamic force |

Presets:

- **Nominal:** 250 km/h, 100% tension, 1× turbulence.
- **Stress test:** 350 km/h, 50% tension, 3.5× turbulence.

The stress-test preset is a plausible simulation scenario, not a certification test.

### Validation view

Open **VALIDATION** for:

- EN 50318 numerical reference-range checks at 250 and 300 km/h;
- PINN-versus-classical-solver force overlay and RMSE;
- predictor and control timing;
- live reduced-model versus distributed-model shadow status;
- 36-mode versus higher-resolution modal consistency;
- the machine-readable physical-calibration/claim boundary.

## Journey logging and accessible exports

The human-facing core workflow is post-journey audit, not manual train control. Live
3D motion and fast charts are difficult to inspect with screen readers, on low-end
hardware, or at a slower cognitive pace. AeroPINN therefore preserves the same data as
persistent text and downloadable files.

### Automatic lifecycle

- Every WebSocket simulation automatically creates a journey; there is no record
  button to forget.
- Journey IDs are stable 32-character hexadecimal identifiers.
- The searchable catalogue is stored in SQLite.
- Telemetry and events are append-only NDJSON files.
- Summaries checkpoint about once per simulated second.
- Clean disconnects finalize as `COMPLETED`; unfinished sessions found after restart
  become `INTERRUPTED`.
- Running journeys cannot be archived or deleted.
- Permanent deletion requires typing the full session ID and remains represented in
  the catalogue audit log.

On first backend startup, the warm-up worker also creates one deterministic sample if
none exists. It uses the production `Engine`: a nominal phase transitions to 350 km/h,
50% tension, 3.5× turbulence, and then a 70 N gust. Its source remains explicitly
labelled `SIMULATION`; outcome values are calculated, not hand-written.

Default storage is `data/journeys/`, excluded from Git. Override it with
`AEROPINN_DATA_DIR`.

### Recorded streams

| Stream | Approximate rate | Purpose |
|---|---:|---|
| `physics_audit_1khz` | 1,000 Hz | Compact native plant, controller, estimator, sensor, force, motion, ripple, and timing evidence |
| `dashboard_frame_30hz` | 30 Hz | Complete nested frame sent to the dashboard |
| `configuration_snapshot_1hz` | 1 Hz | Pantograph, disturbance, catenary, actuator, sensor, controller, PINN, solver, and operating constants |
| Event stream | Transitions/actions | Journey lifecycle, scenario changes, contact loss, gust, EKF fallback, and debounced actuator saturation |

Each telemetry record also carries schema version, session ID, UTC capture time,
interpolated route chainage, latitude, and longitude.

The 1 kHz stream is intentionally detailed and can become large during long sessions.
This repository does not currently impose quotas or automatic retention. Production
deployment should define storage capacity, rotation, archival, encryption, and access
control before collecting operational data.

### Journey documentation

The **JOURNEY LOGS** interface lets users label or correct:

- train name and identifier;
- route name and identifier;
- origin, destination, direction, and track;
- start/end chainage and GPS coordinates;
- ambient and wire temperature;
- wind speed and weather description;
- scenario/journey name.

The browser offers bounded, byte-cursor pages for events, 1 kHz physics, 1 Hz
constants, and dashboard frames, so reviewing a long journey does not load the whole
file into memory.

### Export formats

- **CSV:** flattened dotted columns for spreadsheets, scripts, screen readers, and
  accessibility/sonification tools.
- **JSON:** journey catalogue metadata, summary, events, and complete nested telemetry.
- **ZIP audit package:**
  - `telemetry.csv`
  - `physics_1khz.csv`
  - `dashboard_30hz.csv`
  - `constants_1hz.csv`
  - `events.csv`
  - `telemetry.json`
  - `events.json`
  - `summary.json`
  - `data_dictionary.md`
  - `README.md`
  - `manifest.json` with file sizes and SHA-256 integrity hashes

Exports snapshot the current byte boundary, allowing a running journey to be exported
without reading a partially written record. Full workflow and schema notes live in
[docs/JOURNEY_DATA_ACCESSIBILITY.md](docs/JOURNEY_DATA_ACCESSIBILITY.md).

## Quick start

Requirements:

- Python 3.10 or newer;
- Node.js 18 or newer and npm;
- a modern browser with WebGL for the 3D scene;
- Git for development.

Developed with Python 3.14 and Node.js 24. CUDA is not required.

### One command on Linux/macOS

```bash
git clone https://github.com/ChandraguptSharma07/faraway.git
cd faraway
bash run_local.sh
```

Or, after cloning:

```bash
make up
```

The script creates `.venv`, installs CPU PyTorch and backend/frontend dependencies,
then starts:

- backend: `http://localhost:8000`
- frontend: `http://localhost:5173`

Press `Ctrl+C` to stop both.

## Manual installation

Using explicit virtual-environment paths avoids shell-specific activation problems.

### Linux/macOS, including Fish

From the project root:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install torch --index-url https://download.pytorch.org/whl/cpu
.venv/bin/python -m pip install -r backend/requirements.txt

cd frontend
npm ci
```

Start the backend in terminal 1:

```bash
cd /path/to/faraway
.venv/bin/python -m uvicorn backend.server.app:app --port 8000
```

Start the frontend in terminal 2:

```bash
cd /path/to/faraway/frontend
npm run dev
```

Fish users who prefer activation can run `source .venv/bin/activate.fish`; Bash/Zsh
users can run `source .venv/bin/activate`.

### Windows PowerShell

```powershell
py -m venv .venv
.venv\Scripts\python.exe -m pip install torch --index-url https://download.pytorch.org/whl/cpu
.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
cd frontend
npm ci
```

Then start the backend with `.venv\Scripts\python.exe -m uvicorn
backend.server.app:app --port 8000` from the project root and `npm run dev` from
`frontend` in another terminal.

## Running and deployment

### Development mode

Vite serves the frontend and proxies `/api` and `/ws` to `127.0.0.1:8000`. If Vite
chooses a different port because 5173 is occupied, open the URL it prints; the proxy
still applies.

Useful checks:

```bash
curl http://localhost:8000/health
curl http://localhost:8000/api/calibration-status
```

### Single-origin production build

Build the frontend **before** starting FastAPI:

```bash
cd frontend
npm ci
npm run build
cd ..
.venv/bin/python -m uvicorn backend.server.app:app --host 0.0.0.0 --port 8000
```

When `frontend/dist` exists at backend import time, FastAPI serves the compiled SPA,
assets, REST API, and WebSocket from the same origin. Open `http://localhost:8000`.

### Docker

```bash
docker build -t aeropinn .
docker run --rm -p 8000:8000 -v aeropinn-data:/app/data aeropinn
```

Open `http://localhost:8000`. The volume preserves journey data across containers.

The repository also includes `render.yaml` for Docker-based Render deployment. Set a
persistent disk or external `AEROPINN_DATA_DIR` for real retention; an ephemeral
container filesystem will not preserve audit history after replacement.

### Optional servo

Flash `hardware/aeropinn_servo/aeropinn_servo.ino` and connect the board over USB.
The backend auto-detects supported serial ports; force one with
`AEROPINN_SERIAL_PORT`. The servo maps the simulated force command to a visible angle
and is only a demo indicator—it does not control the simulated plant or prove hardware
control performance. See [hardware/README.md](hardware/README.md).

## API reference

FastAPI also exposes interactive OpenAPI documentation at `http://localhost:8000/docs`.

### Health and evidence

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/health` | Service and optional servo status |
| `GET` | `/api/validation` | Cached EN 50318 reference-check table |
| `GET` | `/api/overlay?speed_kmh=300` | PINN-versus-solver trace, RMSE, and timing |
| `GET` | `/api/calibration-status` | Machine-readable claim boundary and next evidence gate |
| `GET` | `/api/shadow-validation` | Non-blocking reduced-versus-distributed shadow status |
| `GET` | `/api/modal-calibration` | Non-blocking live 36-mode consistency status |

Shadow endpoints accept operating-point query parameters: `speed_kmh`,
`tension_factor`, `turbulence_gain`, and `gust_active`. Unsupported conditions are
reported as outside the comparison envelope rather than silently accepted.

### Journey API

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/api/journeys?include_archived=false` | List the journey catalogue |
| `GET` | `/api/journeys/{id}` | Fetch metadata, summary, counts, and storage information |
| `GET` | `/api/journeys/{id}/records` | Page events or telemetry with `source`, `cursor`, `limit`, and optional `stream` |
| `PATCH` | `/api/journeys/{id}/metadata` | Update supported journey documentation fields |
| `POST` | `/api/journeys/{id}/archive` | Archive a completed/interrupted journey |
| `DELETE` | `/api/journeys/{id}?confirm={id}` | Permanently delete after exact-ID confirmation |
| `GET` | `/api/journeys/{id}/export?format=csv\|json\|audit` | Download an export |

Record paging supports `events` or `telemetry`, byte cursors from zero, limits from 1
to 100, and these telemetry filters:

- `physics_audit_1khz`
- `dashboard_frame_30hz`
- `configuration_snapshot_1hz`

### WebSocket

Connect to `/ws`. The server emits approximately 30 frames per second. Each connection
starts a separate engine and journey.

Client messages:

```json
{"type":"speed","value":250}
{"type":"tension","value":1.0}
{"type":"turbulence","value":1.0}
{"type":"gust","value":80}
```

Unknown message types are ignored. Accepted numeric controls are clamped by the engine.
Every accepted scenario input is written to the journey event stream.

## Validation and claim boundary

Activate the environment or use `.venv/bin/python` explicitly.

```bash
# Complete automated suite (currently 62 tests)
.venv/bin/python -m pytest backend/tests -q

# EN 50318 reference checks at 250 and 300 km/h
.venv/bin/python -m backend.sim.validate

# Passive versus AeroPINN comparison scenarios
.venv/bin/python -m backend.controller.compare

# Reproducible reduced-versus-distributed shadow report
.venv/bin/python -m backend.validation.shadow --output shadow-report.json

# Frontend static checks and production build
cd frontend
npm run lint
npm run build
```

Retrain the PINN only when intentionally changing training data, model structure, or
physics loss:

```bash
.venv/bin/python -m backend.pinn.train
```

Training regenerates `backend/pinn/pinn_model.pt`. Treat a changed checkpoint as a
material model change: rerun solver overlay, controller, timing, shadow, and full tests,
then record the dataset/configuration provenance.

### Evidence layers

1. **Classical benchmark:** EN 50318-style numerical reference ranges at 250 and
   300 km/h.
2. **PINN agreement:** predictor trace/RMSE against the classical solver and latency
   against the declared deadline.
3. **Closed-loop simulation:** passive versus active force variation, contact loss,
   actuator behavior, sensor/EKF health, and deadline misses.
4. **Cross-model shadow:** reduced live plant versus independently implemented
   distributed candidate, without connecting the candidate to control output.
5. **Modal sensitivity:** 36-mode live response compared with a higher-resolution
   modal reference.
6. **Future measured validation:** component identification, blind route/run validation,
   hardware-in-the-loop, supervised trial, and the applicable railway assurance path.

Passing layers 1–5 validates implementation consistency only. It does not establish
train-specific physical accuracy. The complete measured-data contract is in
[docs/REAL_SYSTEM_CALIBRATION.md](docs/REAL_SYSTEM_CALIBRATION.md); shadow methodology is
in [backend/validation/README.md](backend/validation/README.md).

## Configuration

| Variable | Default | Description |
|---|---|---|
| `AEROPINN_DATA_DIR` | `data/journeys` | Persistent SQLite, NDJSON, and export directory |
| `AEROPINN_SERIAL_PORT` | auto-detect | Optional Arduino/ESP32 serial port |
| `PORT` | `8000` in Docker | Production HTTP/WebSocket port |

Important runtime defaults are defined in code and copied into the 1 Hz constants
stream:

- pantograph/catenary disturbance: `backend/sim/parameters.py`;
- distributed catenary: `backend/catenary/parameters.py`;
- sensor model: `backend/controller/sensors.py`;
- actuator model: `backend/controller/actuator.py`;
- deployed controller: `backend/controller/actuator_mpc.py`;
- runtime engine and support boundary: `backend/server/engine.py`.

Do not change only a dashboard label when changing a physical constant. Update the
model, provenance, validation expectations, tests, documentation, and retrained
checkpoint where applicable.

## Repository guide

```text
faraway/
├── backend/
│   ├── sim/          Classical two-mass model, disturbance, parameters, EN checks
│   ├── catenary/     Distributed wire model, reduction, real-time modal solver
│   ├── pinn/         Dataset generation, PINN model/training/inference, checkpoint
│   ├── controller/   MPC, actuator, sensors, EKF, timing, robustness, comparisons
│   ├── server/       FastAPI app, live engine, journey store/exports, optional servo
│   ├── validation/   Calibration boundary and asynchronous shadow validation
│   └── tests/        Physics, control, timing, logging, API, and validation tests
├── frontend/
│   ├── public/models/lastochka.glb   Optimized browser train asset
│   └── src/
│       ├── components/               3D world, legacy 2D view, charts, logs, validation
│       ├── hooks/useTelemetry.js      WebSocket and bounded live history
│       └── lib/api.js                 REST client
├── hardware/         Optional servo sketch and wiring guide
├── docs/             Accessibility workflow and real-system calibration contract
├── data/journeys/    Runtime logs and exports; generated, persistent, Git-ignored
├── Dockerfile        Multi-stage frontend build + Python runtime
├── render.yaml       Render service definition
├── run_local.sh      Local setup and two-server launcher
├── Makefile          `make up` convenience target
├── CHANGELOG.md      Notable project changes
└── er-9-p_electric_train.glb         Retained candidate asset; not loaded at runtime
```

## Known limitations

- Current physical parameters are benchmark/simulation values, not an identified
  Lastochka, pantograph, or route dataset.
- The Lastochka GLB contributes visual geometry only.
- Only vertical pantograph–catenary dynamics are modeled.
- Live catenary droppers are linearized about a taut state and spatial content is
  truncated to retained modes.
- Thermal expansion, ice, wear evolution, lateral stagger/yaw, full train dynamics,
  multi-pantograph interaction, and detailed 3D aerodynamics are absent.
- Sensor and actuator chains mix published component-scale baselines with explicit
  test-rig assumptions; they are not railway-qualified hardware evidence.
- The idealized active reference is retained only for comparison and must not be
  confused with the sensor/EKF/actuator-in-loop AeroPINN lane.
- Journey storage currently has no authentication, encryption, quota, compression,
  or automatic retention policy.
- FastAPI CORS is permissive for the hackathon demo. Do not expose the service or
  operational data directly to an untrusted network without authentication,
  authorization, transport security, and a privacy/retention policy.
- The optional hobby servo is a visual output device, not a force actuator validation.

## Troubleshooting

### `pip: command not found` or `No module named uvicorn`

Use the virtual environment’s Python directly:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install torch --index-url https://download.pytorch.org/whl/cpu
.venv/bin/python -m pip install -r backend/requirements.txt
.venv/bin/python -m uvicorn backend.server.app:app --port 8000
```

### Fish reports `Unsupported use of '='`

That usually comes from Bash-specific shell syntax. No activation is required when
commands use `.venv/bin/python`. To activate under Fish, use:

```fish
source .venv/bin/activate.fish
```

### Vite reports `Permission denied`

Recreate dependencies in the current environment instead of reusing copied
`node_modules` permissions:

```bash
cd frontend
rm -rf node_modules
npm ci
```

Only remove `frontend/node_modules`, never the project directory.

### Dashboard stays on “connecting to backend”

1. Confirm `http://localhost:8000/health` returns JSON.
2. Start Vite from `frontend/` so its `/ws` proxy is active.
3. Check that ports 8000 and the printed Vite port are reachable.
4. If serving a production build, build `frontend/dist` before starting FastAPI.
5. Behind a reverse proxy, ensure WebSocket upgrade headers are forwarded for `/ws`.

### Pantograph appears stationary

- Confirm telemetry is live rather than `OFFLINE`.
- Use the default labelled `MOTION ×25` view; real displacement at 1× is only
  millimetres and can be sub-pixel at a wide camera angle.
- Watch the unscaled `HEAD ±x.x mm` lane readout to confirm incoming movement.
- Zoom toward the pantograph. Motion amplification never changes physics or exports.

### 3D view is blank or slow

- Use a browser with WebGL enabled and current graphics drivers.
- Disable forced software rendering where possible.
- Close duplicate dashboard tabs: each tab creates its own engine and journey.
- The renderer already uses a pixel budget on high-DPI displays; reduced-motion OS
  settings also reduce some visual effects.

### Port already in use

Stop the older process or start on another port. If changing the backend port during
development, also update `frontend/vite.config.js` proxy targets.

### PyTorch installation downloads a large CUDA build

Install CPU PyTorch first from the CPU index, then install the remaining requirements:

```bash
.venv/bin/python -m pip install torch --index-url https://download.pytorch.org/whl/cpu
.venv/bin/python -m pip install -r backend/requirements.txt
```

## 3D asset attribution

The browser demo uses a performance-optimized, lead-car derivative of
[Lastochka electric train](https://sketchfab.com/3d-models/lastochka-electric-train-1e2e86e317164b5983a000f79c6fe7a2)
by tiunov.se, licensed under [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/).
The telemetry-driven pantograph, contact wire, rails, effects, and scene integration
are custom AeroPINN geometry/code. The original model was pruned and optimized for
real-time browser use.

No repository-wide software license file is currently included. Add one before
redistributing the project beyond the terms that apply to its individual assets and
dependencies.
