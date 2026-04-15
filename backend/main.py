"""FastAPI entrypoint for the LogFlow Anomaly Engine."""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse

from .config import settings
from .pipeline import Pipeline
from .schemas import RuleCreate


pipeline = Pipeline()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    await pipeline.start()
    try:
        yield
    finally:
        await pipeline.stop()


app = FastAPI(
    title="LogFlow Anomaly Engine",
    version="0.2.0",
    description="Real-time log stream anomaly detection with incident correlation and blast-radius mapping.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---- health & snapshot ---------------------------------------------------

@app.get("/api/health")
async def health() -> dict:
    return {"status": "ok", "uptime_seconds": pipeline.state.start_ts}


@app.get("/api/stats")
async def stats() -> JSONResponse:
    return JSONResponse(pipeline.snapshot().model_dump())


# ---- scenarios -----------------------------------------------------------

@app.get("/api/scenarios")
async def scenarios() -> dict:
    return {
        "scenarios": pipeline.list_scenarios(),
        "active": pipeline.active_scenarios(),
    }


@app.post("/api/scenarios/{name}")
async def trigger_scenario(name: str) -> dict:
    ok = pipeline.inject_scenario(name)
    return {"ok": ok, "name": name}


# ---- incidents -----------------------------------------------------------

@app.get("/api/incidents")
async def incidents_list() -> JSONResponse:
    return JSONResponse([i.model_dump() for i in pipeline.list_incidents()])


# ---- traces --------------------------------------------------------------

@app.get("/api/traces/recent")
async def traces_recent(
    limit: int = Query(30, ge=1, le=100),
    errors_only: bool = Query(False),
) -> dict:
    return {"trace_ids": pipeline.recent_trace_ids(limit=limit, errors_only=errors_only)}


@app.get("/api/trace/{trace_id}")
async def trace_detail(trace_id: str) -> JSONResponse:
    trace = pipeline.get_trace(trace_id)
    if trace is None:
        raise HTTPException(status_code=404, detail="trace not found")
    return JSONResponse(trace.model_dump())


# ---- service detail ------------------------------------------------------

@app.get("/api/service/{name}")
async def service_detail(name: str) -> JSONResponse:
    detail = pipeline.get_service_detail(name)
    if detail is None:
        raise HTTPException(status_code=404, detail="service not found or idle")
    return JSONResponse(detail.model_dump())


# ---- templates -----------------------------------------------------------

@app.get("/api/templates")
async def templates_list(
    limit: int = Query(80, ge=1, le=300),
    service: str | None = Query(None),
    level: str | None = Query(None),
) -> JSONResponse:
    items = pipeline.get_templates(limit=limit, service=service, level=level)
    return JSONResponse([t.model_dump() for t in items])


# ---- search --------------------------------------------------------------

@app.get("/api/search")
async def search(
    q: str = Query("", max_length=200),
    service: str | None = Query(None),
    level: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
) -> JSONResponse:
    result = pipeline.search_logs(query=q, service=service, level=level, limit=limit)
    return JSONResponse(result.model_dump())


# ---- correlations --------------------------------------------------------

@app.get("/api/correlations")
async def correlations() -> JSONResponse:
    return JSONResponse(pipeline.correlation().model_dump())


# ---- rules ---------------------------------------------------------------

@app.get("/api/rules")
async def rules_list() -> JSONResponse:
    return JSONResponse([r.model_dump() for r in pipeline.list_rules()])


@app.post("/api/rules")
async def rules_add(body: RuleCreate) -> JSONResponse:
    r = pipeline.add_rule(
        name=body.name, service=body.service, metric=body.metric,
        op=body.op, threshold=body.threshold, duration_s=body.duration_s,
    )
    return JSONResponse(r.model_dump())


@app.delete("/api/rules/{rid}")
async def rules_delete(rid: str) -> dict:
    return {"ok": pipeline.delete_rule(rid)}


@app.post("/api/rules/{rid}/toggle")
async def rules_toggle(rid: str, enabled: bool = Query(True)) -> JSONResponse:
    r = pipeline.toggle_rule(rid, enabled)
    if r is None:
        raise HTTPException(status_code=404, detail="rule not found")
    return JSONResponse(r.model_dump())


# ---- prometheus ----------------------------------------------------------

@app.get("/metrics", response_class=PlainTextResponse)
async def metrics() -> str:
    return pipeline.prometheus()


# ---- websocket -----------------------------------------------------------

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
