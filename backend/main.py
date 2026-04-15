"""FastAPI entrypoint for the LogFlow Anomaly Engine."""
from __future__ import annotations

import asyncio
import json
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .config import settings
from .pipeline import Pipeline


pipeline = Pipeline()


@asynccontextmanager
async def lifespan(app: FastAPI):
    await pipeline.start()
    try:
        yield
    finally:
        await pipeline.stop()


app = FastAPI(
    title="LogFlow Anomaly Engine",
    version="0.1.0",
    description="Real-time log stream anomaly detection with blast-radius mapping.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
async def health() -> dict:
    return {
        "status": "ok",
        "uptime_seconds": pipeline.state.start_ts,
    }


@app.get("/api/stats")
async def stats() -> JSONResponse:
    snap = pipeline.snapshot()
    return JSONResponse(snap.model_dump())


@app.get("/api/scenarios")
async def scenarios() -> dict:
    return {"scenarios": pipeline.list_scenarios()}


@app.post("/api/scenarios/{name}")
async def trigger_scenario(name: str) -> dict:
    ok = pipeline.inject_scenario(name)
    return {"ok": ok, "name": name}


@app.websocket("/ws/stream")
async def ws_stream(ws: WebSocket) -> None:
    await ws.accept()
    try:
        while True:
            snap = pipeline.snapshot()
            await ws.send_text(snap.model_dump_json())
            await asyncio.sleep(settings.ws_period_seconds)
    except WebSocketDisconnect:
        return
    except Exception:
        try:
            await ws.close()
        except Exception:
            pass
