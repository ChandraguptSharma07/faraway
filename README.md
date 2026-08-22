# AeroPINN

**Active aerodynamic stabilization of high-speed train pantographs, driven by a
Physics-Informed Neural Network (PINN) used as an ultra-fast predictor inside a
predictive control loop.**

Above ~160 km/h, aerodynamic turbulence and the catenary's span-to-span stiffness
variation make the pantograph–wire **contact force** fluctuate. Lost contact fires a
high-energy arc that wears the carbon strip and the contact wire, capping safe speed.
AeroPINN predicts near-future contact force in milliseconds and a controller commands a
counter-force that keeps contact force flat.

The PINN is a **fast predictor, not a black-box controller**: it answers *"given the
current state and a candidate control force, what is the contact force a few ms from
now?"* A separate predictive controller uses those predictions to choose the best
counter-force.

## Validated against EN 50318

The classical solver reproduces the **EN 50318** reference pantograph–catenary dynamic
interaction model and lands inside the standard's published result ranges at 250 and
300 km/h (mean contact force, standard deviation, statistical max/min, uplift). The demo
then pushes **beyond** the validated envelope — higher speed, degraded contact-wire
tension, raised turbulence — where the **passive** pantograph begins losing contact and
arcing while **AeroPINN holds contact**.

## Architecture

```
  Classical solver  ──trains──►  PINN (predictor)  ──used by──►  Predictive controller
  (EN 50318 ground truth)        (PyTorch, CPU, ~ms)              (short-horizon search)
          │                                                              │
          └──────────────► FastAPI + WebSocket server ◄─────────────────┘
                                       │
                           React + Three.js frontend
                     (3D digital twin + live instruments)
                                       │
                            (optional) ESP32 servo over serial
```

- `backend/sim/`        — classical two-mass solver + multi-span catenary disturbance
- `backend/pinn/`       — PyTorch PINN (data + ODE-residual loss), trained model
- `backend/controller/` — PINN-MPC short-horizon predictive controller
- `backend/server/`     — FastAPI + WebSocket streaming server
- `frontend/`           — React + Three.js digital twin (live pantographs + uPlot traces)
- `hardware/`           — ESP32/Arduino servo sketch + wiring notes (optional)

## Headline metrics

1. **PINN inference latency** (ms on CPU) vs classical solver per-step time.
2. **PINN-vs-solver accuracy** (RMSE + overlay).

Live scoreboard: **contact-force standard deviation** and **% time in contact loss /
arcing**, passive vs AeroPINN.

## Setup & run

### Backend

```bash
python -m venv .venv
# Windows PowerShell:  .venv\Scripts\Activate.ps1
# Git Bash / macOS / Linux:  source .venv/Scripts/activate  (or .venv/bin/activate)

# CPU-only torch from the PyTorch CPU index, then the rest:
pip install torch --index-url https://download.pytorch.org/whl/cpu
pip install -r backend/requirements.txt

# run the server (Step 5+):
python -m uvicorn backend.server.app:app --port 8000
```

### Frontend

```bash
cd frontend
npm install
npm run dev        # serves on http://localhost:5173
```

### Optional hardware (servo)

Flash the sketch in `hardware/` to an ESP32/Arduino and connect over USB. The backend
auto-detects the serial port and twitches the servo in sync with the control command.

> **Runs fully without hardware.** If no board is connected, the entire software demo runs
> normally — the servo is purely additive and never a dependency.

## Validation & development

```bash
# EN 50318 validation gate (prints the comparison table at 250 & 300 km/h)
python -m backend.sim.validate

# passive vs AeroPINN comparison (headline metrics across scenarios)
python -m backend.controller.compare

# tests (solver validation, PINN latency, controller beats passive)
python -m pytest backend/tests -q

# retrain the PINN (a trained model is committed at backend/pinn/pinn_model.pt; ~3 min CPU)
python -m backend.pinn.train
```

The trained model (`backend/pinn/pinn_model.pt`, ~40 KB) is committed so the demo runs
out of the box; the command above regenerates it.

## 3D model attribution

The browser demo uses a performance-optimized, lead-car derivative of
[Lastochka electric train](https://sketchfab.com/3d-models/lastochka-electric-train-1e2e86e317164b5983a000f79c6fe7a2)
by tiunov.se, licensed under [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/).
The telemetry-driven pantograph, catenary, rails, effects, and scene are custom AeroPINN
geometry. The original train model was pruned and optimized for real-time web use.

## Requirements

Python ≥ 3.10, Node ≥ 18. Developed on Python 3.14 / Node 24. CPU-only — no CUDA/GPU
required.
