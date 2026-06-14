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

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

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


def get_predictor():
    global _predictor
    if _predictor is None:
        from backend.pinn.predict import PINNPredictor
        _predictor = PINNPredictor()
    return _predictor


@app.on_event("startup")
def _warm_caches():
    """Precompute the credibility views in a background thread so /health is up
    immediately and the panel is ready by the time the operator opens it."""
    def work():
        try:
            _compute_validation()
            _compute_overlay(300.0)
        except Exception:
            pass
    threading.Thread(target=work, daemon=True).start()


@app.get("/health")
def health():
    return {"status": "ok", "service": "aeropinn"}


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
    lat = pred.benchmark_latency()
    res = simulate(kmh_to_ms(speed_kmh), duration=1.5)
    out = {
        "speed_kmh": speed_kmh,
        "t": [round(float(x), 4) for x in ov["t"]],
        "f_pinn": [round(float(x), 2) for x in ov["f_pinn"]],
        "f_solver": [round(float(x), 2) for x in ov["f_solver"]],
        "rmse_N": round(ov["rmse_N"], 3),
        "pinn_latency_ms": round(lat["latency_ms_batch"], 4),
        "pinn_latency_ms_single": round(lat["latency_ms_single"], 4),
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
    engine = Engine()
    target_dt = 0.02  # 50 fps, real-time (20 sim steps of 1 ms per frame)
    n_sub = int(round(target_dt / engine.dt))
    stop = asyncio.Event()

    async def receiver():
        try:
            while not stop.is_set():
                msg = await ws.receive_json()
                _handle_input(engine, msg)
        except (WebSocketDisconnect, Exception):
            stop.set()

    async def streamer():
        try:
            while not stop.is_set():
                t0 = time.perf_counter()
                engine.step(n_sub)
                await ws.send_json(engine.frame())
                await asyncio.sleep(max(0.0, target_dt - (time.perf_counter() - t0)))
        except (WebSocketDisconnect, Exception):
            stop.set()

    await asyncio.gather(receiver(), streamer())
