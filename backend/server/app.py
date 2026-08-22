"""AeroPINN FastAPI server.

WebSocket /ws streams the live dual simulation (passive vs AeroPINN) and accepts
control inputs (speed, gust, tension, turbulence). HTTP endpoints serve the
credibility view: EN 50318 validation table, PINN-vs-solver overlay, and latency.

Run:  python -m uvicorn backend.server.app:app --port 8000
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
import threading
import time
import traceback

import os
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from backend.server.engine import Engine


@asynccontextmanager
async def _lifespan(_app: FastAPI):
    """Warm evidence caches off-loop and close their workers on shutdown.

    Args:
        _app (FastAPI): The FastAPI application instance.

    Yields:
        None: Yields control back to the FastAPI application during its lifespan.
    """
    def work():
        try:
            _compute_validation()
            _compute_overlay(300.0)
            from backend.server.journeys import ensure_sample_journey

            ensure_sample_journey(get_journey_store(), get_predictor())
            get_shadow_service().warm()
            get_modal_shadow_service().warm()
        except Exception:
            # Endpoints expose background calculation errors without preventing
            # the live server from starting.
            pass

    threading.Thread(target=work, daemon=True).start()
    yield
    if _shadow_service is not None:
        _shadow_service.close()
    if _modal_shadow_service is not None:
        _modal_shadow_service.close()


app = FastAPI(title="AeroPINN", lifespan=_lifespan)
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
_journey_store = None


def get_predictor():
    """Retrieve or initialize the singleton PINN predictor instance.

    Returns:
        PINNPredictor: The initialized PINN predictor instance used for physics-informed neural network predictions.
    """
    global _predictor
    if _predictor is None:
        from backend.pinn.predict import PINNPredictor
        _predictor = PINNPredictor()
    return _predictor


def get_servo():
    """Optional hardware servo link (auto-detected; no-op if no board).

    Returns:
        ServoLink: The hardware servo link singleton instance.
    """
    global _servo
    if _servo is None:
        from backend.server.servo import ServoLink
        _servo = ServoLink()
    return _servo


def get_journey_store():
    """Retrieve or initialize the singleton journey store instance.

    Returns:
        JourneyStore: The journey store for recording and managing simulation sessions.
    """
    global _journey_store
    if _journey_store is None:
        from backend.server.journeys import JourneyStore

        _journey_store = JourneyStore()
    return _journey_store



_modal_shadow_service = None
def get_modal_shadow_service():
    """Retrieve or initialize the modal shadow validation service singleton.

    Returns:
        ShadowValidationService: Service for performing background modal calibration.
    """
    global _modal_shadow_service
    if _modal_shadow_service is None:
        from backend.validation.shadow import ShadowValidationService, run_modal_calibration_scenario
        _modal_shadow_service = ShadowValidationService(
            runner=run_modal_calibration_scenario,
            authoritative_model="distributed-v1",
        )
    return _modal_shadow_service

def get_shadow_service():
    """Background-only model comparison; never connected to control output.

    Returns:
        ShadowValidationService: Service running in the background for shadow validation without affecting active control.
    """
    global _shadow_service
    if _shadow_service is None:
        from backend.validation.shadow import ShadowValidationService
        _shadow_service = ShadowValidationService()
    return _shadow_service


@app.get("/health")
def health():
    """Check the health status of the AeroPINN server and connected hardware.

    Returns:
        dict: A dictionary containing the service status and any servo board status information.
    """
    return {"status": "ok", "service": "aeropinn", **get_servo().status()}


def _compute_validation():
    """Compute and cache the EN 50318 validation metrics.

    Calculates the standard contact force validation metrics at 250 km/h and 300 km/h
    and caches the results.

    Returns:
        dict: A dictionary containing the validation rows and solver step times for each speed.
    """
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
    """Compute and cache the overlay comparing PINN predictions with the classical solver.

    Args:
        speed_kmh (float): The simulation speed in kilometers per hour.

    Returns:
        dict: A dictionary containing time series data, latency metrics, and RMSE comparing the PINN to the classical solver.
    """
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
    """EN 50318 validation table for the credibility view (cached).

    Returns:
        dict: Pre-computed validation metrics for the credibility dashboard.
    """
    return _compute_validation()


@app.get("/api/calibration-status")
def physical_calibration_status():
    """Expose what physical fidelity is and is not supported by evidence.

    Returns:
        dict: A dictionary summarizing the physical calibration status of the system.
    """
    from backend.validation.calibration import calibration_status

    return calibration_status()


@app.get("/api/journeys")
def list_journeys(include_archived: bool = False):
    """List all recorded simulation journeys.

    Args:
        include_archived (bool, optional): Whether to include archived journeys in the response. Defaults to False.

    Returns:
        dict: A dictionary containing a list of journeys.
    """
    return {"journeys": get_journey_store().list(include_archived)}


@app.get("/api/journeys/{journey_id}")
def get_journey(journey_id: str):
    """Retrieve details of a specific simulation journey.

    Args:
        journey_id (str): The unique identifier of the journey.

    Returns:
        dict: Details and metadata for the specified journey.

    Raises:
        HTTPException: If the journey is not found.
    """
    try:
        return get_journey_store().get(journey_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="journey not found") from exc


@app.get("/api/journeys/{journey_id}/records")
def get_journey_records(
    journey_id: str,
    source: str = "events",
    cursor: int = 0,
    limit: int = 25,
    stream: str | None = None,
):
    """Bounded text view over persistent logs; byte cursors scale to large journeys.

    Args:
        journey_id (str): The unique identifier of the journey.
        source (str, optional): The log source to query. Defaults to "events".
        cursor (int, optional): The byte cursor for pagination. Defaults to 0.
        limit (int, optional): The maximum number of records to return. Defaults to 25.
        stream (str | None, optional): Stream configuration identifier. Defaults to None.

    Returns:
        dict: A paginated set of journey records.

    Raises:
        HTTPException: If the journey is not found or parameters are invalid.
    """
    try:
        return get_journey_store().page(
            journey_id, source, cursor=cursor, limit=limit, stream=stream
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="journey not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.patch("/api/journeys/{journey_id}/metadata")
def update_journey_metadata(journey_id: str, changes: dict):
    """Update metadata for a specific simulation journey.

    Args:
        journey_id (str): The unique identifier of the journey.
        changes (dict): A dictionary of metadata updates to apply.

    Returns:
        dict: The updated journey metadata.

    Raises:
        HTTPException: If the journey is not found or updates are invalid.
    """
    try:
        metadata = get_journey_store().update_metadata(journey_id, changes)
        return {"id": journey_id, "metadata": metadata}
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="journey not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/journeys/{journey_id}/archive")
def archive_journey(journey_id: str):
    """Archive a specific simulation journey.

    Args:
        journey_id (str): The unique identifier of the journey.

    Returns:
        dict: Confirmation of the archival status.

    Raises:
        HTTPException: If the journey is not found or cannot be archived.
    """
    try:
        return get_journey_store().archive(journey_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="journey not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.delete("/api/journeys/{journey_id}", status_code=204)
def delete_journey(journey_id: str, confirm: str):
    """Permanently delete a simulation journey.

    Args:
        journey_id (str): The unique identifier of the journey.
        confirm (str): A confirmation string to authorize the deletion.

    Raises:
        HTTPException: If the journey is not found, or if confirmation fails.
    """
    try:
        get_journey_store().delete(journey_id, confirm)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="journey not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.get("/api/journeys/{journey_id}/export")
def export_journey(journey_id: str, format: str = "audit"):
    """Export the data of a specific simulation journey as a file.

    Args:
        journey_id (str): The unique identifier of the journey.
        format (str, optional): The export format. Defaults to "audit".

    Returns:
        FileResponse: The exported journey data file.

    Raises:
        HTTPException: If the journey is not found or format is invalid.
    """
    try:
        path, media_type = get_journey_store().export(journey_id, format)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="journey not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return FileResponse(path, media_type=media_type, filename=path.name)


@app.get("/api/overlay")
def overlay(speed_kmh: float = 300.0):
    """PINN-predicted vs classical-solver contact force + timing (cached).

    Args:
        speed_kmh (float, optional): The vehicle speed in km/h. Defaults to 300.0.

    Returns:
        dict: Overlay metric data comparing the solver output with the PINN output.
    """
    return _compute_overlay(speed_kmh)


@app.get("/api/shadow-validation")
def shadow_validation(
    speed_kmh: float = 250.0,
    tension_factor: float = 1.0,
    turbulence_gain: float = 1.0,
    gust_active: bool = False,
):
    """Non-blocking reduced-vs-distributed benchmark status.

    Args:
        speed_kmh (float, optional): Simulation speed in km/h. Defaults to 250.0.
        tension_factor (float, optional): Scaling factor for wire tension. Defaults to 1.0.
        turbulence_gain (float, optional): Gain for aerodynamic turbulence. Defaults to 1.0.
        gust_active (bool, optional): Whether an active wind gust is applied. Defaults to False.

    Returns:
        dict: The current snapshot of the shadow validation metrics.
    """
    from backend.validation.shadow import classify_operating_point

    snapshot = get_shadow_service().snapshot()
    snapshot["operating_point"] = classify_operating_point(
        snapshot, speed_kmh, tension_factor, turbulence_gain, gust_active
    )
    return snapshot



@app.get("/api/modal-calibration")
def modal_calibration(
    speed_kmh: float = 250.0,
    tension_factor: float = 1.0,
    turbulence_gain: float = 1.0,
    gust_active: bool = False,
):
    """Retrieve modal calibration snapshot for the requested operating point.

    Args:
        speed_kmh (float, optional): Simulation speed in km/h. Defaults to 250.0.
        tension_factor (float, optional): Scaling factor for wire tension. Defaults to 1.0.
        turbulence_gain (float, optional): Gain for aerodynamic turbulence. Defaults to 1.0.
        gust_active (bool, optional): Whether an active wind gust is applied. Defaults to False.

    Returns:
        dict: A snapshot dictionary containing modal calibration status.
    """
    from backend.validation.shadow import classify_operating_point
    snapshot = get_modal_shadow_service().snapshot()
    snapshot["operating_point"] = classify_operating_point(
        snapshot, speed_kmh, tension_factor, turbulence_gain, gust_active
    )
    return snapshot

def _handle_input(engine: Engine, msg: dict, journey=None):
    """Process incoming WebSocket control messages and apply them to the engine.

    Args:
        engine (Engine): The active simulation engine instance.
        msg (dict): The incoming control message payload.
        journey (Journey, optional): The active journey instance to record the input event. Defaults to None.
    """
    kind = msg.get("type")
    val = msg.get("value")
    if kind == "speed":
        engine.set_speed(val)
        applied = engine.rp.speed_kmh
    elif kind == "tension":
        engine.set_tension(val)
        applied = engine.rp.tension_factor
    elif kind == "turbulence":
        engine.set_turbulence(val)
        applied = engine.rp.turbulence_gain
    elif kind == "gust":
        applied = val if val is not None else 70.0
        engine.trigger_gust(applied)
    else:
        return
    if journey is not None:
        journey.event("SCENARIO_INPUT", {
            "type": kind,
            "requested_value": val,
            "applied_value": applied,
        })


@app.websocket("/ws")
async def ws(ws: WebSocket):
    """WebSocket endpoint for real-time dual simulation streaming and control.

    Args:
        ws (WebSocket): The connected WebSocket instance.
    """
    await ws.accept()
    # Run the initial warm-up in a thread so we don't block other connections/health checks
    engine = await asyncio.to_thread(Engine, predictor=get_predictor())
    journey = get_journey_store().create()
    journey.event("JOURNEY_STARTED", {"automatic": True})
    servo = get_servo()  # optional; no-op without a board
    target_dt = 0.033  # ~30 fps, eased for Render CPU limits (33 sim steps of 1 ms per frame)
    n_sub = int(round(target_dt / engine.dt))
    stop = asyncio.Event()
    journey_status = ["COMPLETED"]

    async def receiver():
        """Listen for and process incoming WebSocket messages."""
        try:
            while not stop.is_set():
                msg = await ws.receive_json()
                _handle_input(engine, msg, journey)
        except WebSocketDisconnect:
            pass
        except Exception:
            journey_status[0] = "INTERRUPTED"
            traceback.print_exc()
        finally:
            stop.set()

    async def streamer():
        """Run the simulation step and stream the frame output to the WebSocket."""
        try:
            while not stop.is_set():
                t0 = time.perf_counter()
                # Run the heavy simulation step in a background thread
                await asyncio.to_thread(
                    engine.step, n_sub, journey.record_physics
                )
                servo.send(engine.f_actuator_estimate)  # bounded hardware estimate
                frame = engine.frame()
                frame["journey"] = {
                    "id": journey.id,
                    "status": "RUNNING",
                    "started_at": journey.started_at,
                    "schema_version": "aeropinn-journey-v1",
                }
                journey.record(frame)
                journey.record_constants(engine.constants_snapshot())
                await ws.send_json(frame)
                await asyncio.sleep(max(0.0, target_dt - (time.perf_counter() - t0)))
        except WebSocketDisconnect:
            pass
        except Exception:
            journey_status[0] = "INTERRUPTED"
            traceback.print_exc()
        finally:
            stop.set()

    tasks = [asyncio.create_task(receiver()), asyncio.create_task(streamer())]
    try:
        _, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        for task in pending:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
    finally:
        journey.finalize(journey_status[0])


# Serve static files from the frontend/dist directory if it exists
static_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "frontend", "dist")
if os.path.exists(static_path):
    app.mount("/assets", StaticFiles(directory=os.path.join(static_path, "assets")), name="assets")

    @app.get("/{full_path:path}")
    async def serve_frontend(full_path: str):
        """Serve the compiled frontend application.

        Args:
            full_path (str): The requested path from the client.

        Returns:
            FileResponse: The requested static file or the SPA index.html fallback.

        Raises:
            HTTPException: If an unhandled API or WebSocket path is matched.
        """
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
