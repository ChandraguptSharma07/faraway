"""Throwaway WebSocket spine — Step 0 de-risking only.

Minimal FastAPI app that streams an incrementing counter every 100 ms over a
WebSocket. Its only job is to prove the backend<->frontend round-trip works on
this machine (ports, CORS, localhost) before any real features are built. The
real server (Step 5) supersedes this; this file can then be deleted.

Run:  .venv/Scripts/python.exe -m uvicorn backend.server.spine:app --port 8000
"""

from __future__ import annotations

import asyncio
import time

from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="AeroPINN spine (throwaway)")

# Permissive CORS for local dev (Vite on :5173). WebSocket handshakes are not
# subject to CORS preflight, but the later HTTP endpoints will be.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "service": "spine"}


@app.websocket("/ws/spine")
async def ws_spine(ws: WebSocket) -> None:
    await ws.accept()
    counter = 0
    try:
        while True:
            await ws.send_json({"counter": counter, "t": round(time.time(), 3)})
            counter += 1
            await asyncio.sleep(0.1)  # 100 ms cadence
    except Exception:
        # Client disconnected — exit quietly.
        return
