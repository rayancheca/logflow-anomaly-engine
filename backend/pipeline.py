"""End-to-end async pipeline that glues every component together.

    generator ─▶ stream bus ─┬─▶ storage consumer ─▶ DuckDB
                              └─▶ drain consumer   ─▶ template miner

    + periodic task: detector loop reads storage + drain, produces anomalies,
                     attaches blast-radius from the service graph.

The pipeline exposes a `state` object the FastAPI layer reads on every
websocket tick.
"""
from __future__ import annotations

import asyncio
import time
from collections import deque
from dataclasses import dataclass, field

from .config import settings
from .detector import AnomalyDetector
from .drain import Drain
from .generator import Generator
from .graph import ServiceGraph
from .schemas import Anomaly, Kpi, LogRecord, StreamMessage, TimelinePoint
from .storage import Storage
from .stream_bus import StreamBus


@dataclass
class PipelineState:
    start_ts: float = field(default_factory=time.time)
    storage: Storage = field(default_factory=lambda: Storage(settings.duckdb_path))
    bus: StreamBus = field(default_factory=StreamBus)
    generator: Generator = field(default_factory=Generator)
    drain: Drain = field(default_factory=lambda: Drain(depth=4, similarity_threshold=0.55))
    graph: ServiceGraph = field(default_factory=ServiceGraph)
    detector: AnomalyDetector = field(default_factory=lambda: AnomalyDetector(
        zscore_threshold=settings.zscore_threshold,
        contamination=settings.iforest_contamination,
    ))
    template_service: dict[int, str] = field(default_factory=dict)
    anomalies: deque[Anomaly] = field(default_factory=lambda: deque(maxlen=80))
    last_kpi: Kpi | None = None
    last_timeline: list[TimelinePoint] = field(default_factory=list)
    active_scenarios: list[str] = field(default_factory=list)


class Pipeline:
    def __init__(self) -> None:
        self.state = PipelineState()
        self._tasks: list[asyncio.Task] = []
        self._stop = asyncio.Event()

    # ---- lifecycle -----------------------------------------------------

    async def start(self) -> None:
        loop = asyncio.get_running_loop()
        self._stop.clear()
        bus = self.state.bus
        self.state.bus.subscribe("logs", "storage")
        self.state.bus.subscribe("logs", "drain")
        # Hold references to the subscribers we just created
        self._sub_storage = bus._topics["logs"][0]
        self._sub_drain = bus._topics["logs"][1]
        self._tasks = [
            loop.create_task(self._producer_loop(),  name="producer"),
            loop.create_task(self._storage_loop(),   name="storage"),
            loop.create_task(self._drain_loop(),     name="drain"),
            loop.create_task(self._detector_loop(),  name="detector"),
            loop.create_task(self._prune_loop(),     name="pruner"),
        ]

    async def stop(self) -> None:
        self._stop.set()
        for t in self._tasks:
            t.cancel()
        for t in self._tasks:
            try:
                await t
            except (asyncio.CancelledError, Exception):
                pass
        self._tasks = []

    # ---- control -------------------------------------------------------

    def inject_scenario(self, name: str) -> bool:
        sc = self.state.generator.inject(name)
        if sc:
            self.state.active_scenarios.append(name)
            return True
        return False

    def list_scenarios(self) -> list[str]:
        return self.state.generator.scenario_catalog()

    # ---- loops ---------------------------------------------------------

    async def _producer_loop(self) -> None:
        gen = self.state.generator
        bus = self.state.bus
        tick_period = 0.2
        import math
        while not self._stop.is_set():
            now = time.time()
            t = now % 60.0
            base = settings.base_rate
            burst = settings.burst_rate
            rate = base + (burst - base) * max(0.0, math.sin(t / 60.0 * math.tau)) * 0.5
            n = max(1, int(rate * tick_period))
            for r in gen.tick(n, now):
                await bus.publish("logs", r)
            await asyncio.sleep(tick_period)

    async def _storage_loop(self) -> None:
        buf: list[LogRecord] = []
        last_flush = time.time()
        sub = self._sub_storage
        while not self._stop.is_set():
            try:
                r: LogRecord = await asyncio.wait_for(sub.queue.get(), timeout=0.25)
                buf.append(r)
            except asyncio.TimeoutError:
                pass
            if len(buf) >= 100 or (time.time() - last_flush) > 0.5:
                if buf:
                    self.state.storage.insert_many(buf)
                    buf.clear()
                last_flush = time.time()

    async def _drain_loop(self) -> None:
        sub = self._sub_drain
        drain = self.state.drain
        while not self._stop.is_set():
            try:
                r: LogRecord = await asyncio.wait_for(sub.queue.get(), timeout=0.25)
            except asyncio.TimeoutError:
                continue
            tid, is_new = drain.add(r.message)
            r.template_id = tid
            if is_new:
                self.state.template_service[tid] = r.service

    async def _detector_loop(self) -> None:
        period = settings.detector_period_seconds
        while not self._stop.is_set():
            await asyncio.sleep(period)
            try:
                self._run_detection_once()
            except Exception as e:
                # never kill the loop for a single tick failure
                print(f"[detector] error: {e}")

    def _run_detection_once(self) -> None:
        storage = self.state.storage
        aggs = storage.service_rates(settings.window_seconds)
        if not aggs:
            return
        # Update graph + node metrics using the trace pairs we just stored
        pairs = storage.trace_service_pairs(window_seconds=settings.window_seconds)
        self.state.graph.observe(pairs)
        self.state.graph.update_node_metrics(aggs, settings.window_seconds)
        # Run detectors
        new_anoms: list[Anomaly] = []
        new_anoms.extend(self.state.detector.detect_rates(aggs))
        svcs, mat = storage.feature_matrix(settings.window_seconds)
        new_anoms.extend(self.state.detector.detect_features(svcs, mat))
        fresh_templates = self.state.drain.drain_new_templates()
        new_anoms.extend(self.state.detector.detect_templates(
            fresh_templates, self.state.template_service,
        ))
        # Attach blast radius
        for a in new_anoms:
            order, hops = self.state.graph.blast_radius(
                a.service, settings.blast_radius_depth,
            )
            a.blast_radius = order
            a.blast_hops = hops
            self.state.anomalies.append(a)
        # Timeline + KPI snapshot
        timeline = storage.timeline(settings.window_seconds, buckets=60)
        self.state.last_timeline = timeline
        total = sum(p.total for p in timeline)
        errs = sum(p.errors for p in timeline)
        now = time.time()
        anoms_last_min = sum(
            1 for a in self.state.anomalies if (now - a.ts) <= 60.0
        )
        active_services = sum(1 for a in aggs if a["total"] > 0)
        self.state.last_kpi = Kpi(
            logs_per_sec=round(total / max(1, settings.window_seconds), 2),
            error_rate=round(errs / max(1, total), 4),
            active_services=active_services,
            anomalies_last_min=anoms_last_min,
            templates_tracked=self.state.drain.total_templates(),
            window_seconds=settings.window_seconds,
            uptime_seconds=round(now - self.state.start_ts, 1),
        )

    async def _prune_loop(self) -> None:
        while not self._stop.is_set():
            await asyncio.sleep(10.0)
            self.state.storage.prune(settings.window_seconds * 4)
            # also drop old scenario names
            now = time.time()
            self.state.active_scenarios = [
                s for s in self.state.active_scenarios if any(
                    sc.service and (now - sc.started) < sc.ttl
                    for sc in self.state.generator.scenarios
                )
            ]

    # ---- read helpers --------------------------------------------------

    def snapshot(self) -> StreamMessage:
        storage = self.state.storage
        recent_logs = storage.recent_records(limit=40)
        graph_snap = self.state.graph.snapshot()
        kpi = self.state.last_kpi or Kpi(
            logs_per_sec=0.0, error_rate=0.0, active_services=0,
            anomalies_last_min=0, templates_tracked=0,
            window_seconds=settings.window_seconds,
            uptime_seconds=round(time.time() - self.state.start_ts, 1),
        )
        return StreamMessage(
            kind="tick",
            kpi=kpi,
            logs=recent_logs,
            anomalies=list(self.state.anomalies)[-20:],
            graph=graph_snap,
            timeline=self.state.last_timeline or storage.timeline(settings.window_seconds, 60),
        )
