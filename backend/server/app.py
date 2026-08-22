"""AeroPINN FastAPI server.

WebSocket /ws streams the live dual simulation (passive vs AeroPINN) and accepts
control inputs (speed, gust, tension, turbulence). HTTP endpoints serve the
credibility view: EN 50318 validation table, PINN-vs-solver overlay, and latency.

Run:  python -m uvicorn backend.server.app:app --port 8000
"""

from __future__ import annotations

import asyncio
import threading
import time
import traceback

import os
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from backend.server.engine import Engine

app = FastAPI(title="AeroPINN")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Lazy singletons + caches for the (CPU-heavy) credibility views. These are
# deterministic, so we compute once and reuse — the panel then opens instantly.
_predictor = None
_validation_cache = None
_overlay_cache: dict[float, dict] = {}
_servo = None
_shadow_service = None


def get_predictor():
    global _predictor
    if _predictor is None:
        from backend.pinn.predict import PINNPredictor
        _predictor = PINNPredictor()
    return _predictor


def get_servo():
    """Optional hardware servo link (auto-detected; no-op if no board)."""
    global _servo
    if _servo is None:
        from backend.server.servo import ServoLink
        _servo = ServoLink()
    return _servo


def get_shadow_service():
    """Background-only model comparison; never connected to control output."""
    global _shadow_service
    if _shadow_service is None:
        from backend.validation.shadow import ShadowValidationService
        _shadow_service = ShadowValidationService()
    return _shadow_service


@app.on_event("startup")
def _warm_caches():
    """Precompute the credibility views in a background thread so /health is up
    immediately and the panel is ready by the time the operator opens it."""
    def work():
        try:
            _compute_validation()
            _compute_overlay(300.0)
            get_shadow_service().warm()
        except Exception:
            pass
    threading.Thread(target=work, daemon=True).start()


@app.on_event("shutdown")
def _stop_background_services():
    if _shadow_service is not None:
        _shadow_service.close()


@app.get("/health")
def health():
    return {"status": "ok", "service": "aeropinn", **get_servo().status()}


def _compute_validation():
    global _validation_cache
    if _validation_cache is not None:
        return _validation_cache
    from backend.sim.parameters import kmh_to_ms
    from backend.sim.solver import metrics, simulate
    from backend.sim.validate import EN50318, _in_range

    out = {}
    for speed in (250, 300):
        m = metrics(simulate(kmh_to_ms(speed), duration=6.0))
        rows = []
        for key, (lo, hi) in EN50318[speed].items():
            rows.append({
                "metric": key,
                "value": round(m[key], 2),
                "low": lo, "high": hi,
                "pass": _in_range(m[key], lo, hi),
            })
        out[str(speed)] = {"rows": rows, "solver_step_ms": round(m["step_wall_ms"], 4)}
    _validation_cache = out
    return out


def _compute_overlay(speed_kmh: float):
    if speed_kmh in _overlay_cache:
        return _overlay_cache[speed_kmh]
    from backend.pinn.predict import rollout_overlay
    from backend.sim.parameters import kmh_to_ms
    from backend.sim.solver import simulate

    pred = get_predictor()
    ov = rollout_overlay(pred, speed_kmh=speed_kmh, duration=1.5, sample_dt=4.0e-3)
    lat = pred.benchmark_latency(n_candidates=21, deadline_ms=4.0)
    res = simulate(kmh_to_ms(speed_kmh), duration=1.5)
    out = {
        "speed_kmh": speed_kmh,
        "t": [round(float(x), 4) for x in ov["t"]],
        "f_pinn": [round(float(x), 2) for x in ov["f_pinn"]],
        "f_solver": [round(float(x), 2) for x in ov["f_solver"]],
        "rmse_N": round(ov["rmse_N"], 3),
        "pinn_latency_ms": round(lat["latency_ms_batch"], 4),
        "pinn_latency_ms_single": round(lat["latency_ms_single"], 4),
        "pinn_latency_ms_p99": round(lat["latency_ms_p99"], 4),
        "deadline_miss_pct": round(lat["deadline_miss_pct"], 2),
        "control_deadline_ms": lat["deadline_ms"],
        "solver_step_ms": round(res.step_wall_ms, 4),
        "horizon_ms": round(ov["horizon_ms"], 1),
    }
    _overlay_cache[speed_kmh] = out
    return out


@app.get("/api/validation")
def validation():
    """EN 50318 validation table for the credibility view (cached)."""
    return _compute_validation()


@app.get("/api/overlay")
def overlay(speed_kmh: float = 300.0):
    """PINN-predicted vs classical-solver contact force + timing (cached)."""
    return _compute_overlay(speed_kmh)


@app.get("/api/shadow-validation")
def shadow_validation(
    speed_kmh: float = 250.0,
    tension_factor: float = 1.0,
    turbulence_gain: float = 1.0,
    gust_active: bool = False,
):
    """Non-blocking reduced-vs-distributed benchmark status."""
    from backend.validation.shadow import classify_operating_point

    snapshot = get_shadow_service().snapshot()
    snapshot["operating_point"] = classify_operating_point(
        snapshot, speed_kmh, tension_factor, turbulence_gain, gust_active
    )
    return snapshot


def _handle_input(engine: Engine, msg: dict):
    kind = msg.get("type")
    val = msg.get("value")
    if kind == "speed":
        engine.set_speed(val)
    elif kind == "tension":
        engine.set_tension(val)
    elif kind == "turbulence":
        engine.set_turbulence(val)
    elif kind == "gust":
        engine.trigger_gust(val if val is not None else 70.0)


@app.websocket("/ws")
async def ws(ws: WebSocket):
    await ws.accept()
    # Run the initial warm-up in a thread so we don't block other connections/health checks
    engine = await asyncio.to_thread(Engine, predictor=get_predictor())
    servo = get_servo()  # optional; no-op without a board
    target_dt = 0.033  # ~30 fps, eased for Render CPU limits (33 sim steps of 1 ms per frame)
    n_sub = int(round(target_dt / engine.dt))
    stop = asyncio.Event()

    async def receiver():
        try:
            while not stop.is_set():
                msg = await ws.receive_json()
                _handle_input(engine, msg)
        except WebSocketDisconnect:
            pass
        except Exception:
            traceback.print_exc()
        finally:
            stop.set()

    async def streamer():
        try:
            while not stop.is_set():
                t0 = time.perf_counter()
                # Run the heavy simulation step in a background thread
                await asyncio.to_thread(engine.step, n_sub)
                servo.send(engine.f_actuator_estimate)  # bounded hardware estimate
                await ws.send_json(engine.frame())
                await asyncio.sleep(max(0.0, target_dt - (time.perf_counter() - t0)))
        except WebSocketDisconnect:
            pass
        except Exception:
            traceback.print_exc()
        finally:
            stop.set()

    await asyncio.gather(receiver(), streamer())


# Serve static files from the frontend/dist directory if it exists
static_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "frontend", "dist")
if os.path.exists(static_path):
    app.mount("/assets", StaticFiles(directory=os.path.join(static_path, "assets")), name="assets")

    @app.get("/{full_path:path}")
    async def serve_frontend(full_path: str):
        # Do not serve index.html for missing API or WS routes
        if full_path.startswith("api") or full_path.startswith("ws"):
            from fastapi import HTTPException
            raise HTTPException(status_code=404)

        # Serve favicon or other root files if they exist
        file_path = os.path.join(static_path, full_path)
        if os.path.isfile(file_path):
            return FileResponse(file_path)
        # Fallback to index.html for SPA routing
        return FileResponse(os.path.join(static_path, "index.html"))
