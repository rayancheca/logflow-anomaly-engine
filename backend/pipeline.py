"""End-to-end async pipeline that glues every component together.

    generator ─▶ stream bus ─┬─▶ storage consumer ─▶ DuckDB
                              └─▶ drain consumer   ─▶ template miner

    + periodic detector loop: reads storage + drain, produces anomalies,
      runs the rules engine, attaches blast-radius from the service graph,
      feeds the incident engine, and updates the forecaster.

The pipeline exposes a `snapshot()` view the FastAPI layer reads on every
websocket tick and a handful of deep-dive helpers for REST endpoints.
"""
from __future__ import annotations

import asyncio
import math
import time
from collections import OrderedDict, deque
from dataclasses import dataclass, field

import numpy as np

from .config import settings
from .detector import AnomalyDetector
from .drain import Drain
from .forecast import Forecaster
from .generator import GROUPS, Generator
from .graph import ServiceGraph
from .incidents import IncidentEngine
from .rules import RulesEngine
from .schemas import (
    AlertRule,
    Anomaly,
    CorrelationMatrix,
    Incident,
    Kpi,
    LogRecord,
    SearchResult,
    ServiceDetail,
    ServiceEdge,
    StreamMessage,
    TemplateInfo,
    TimelinePoint,
    Trace,
    TraceSpan,
)
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
    incidents: IncidentEngine = field(default_factory=IncidentEngine)
    rules: RulesEngine = field(default_factory=RulesEngine)
    forecaster: Forecaster = field(default_factory=Forecaster)
    template_service: dict[int, str] = field(default_factory=dict)
    anomalies: deque[Anomaly] = field(default_factory=lambda: deque(maxlen=200))
    last_kpi: Kpi | None = None
    last_timeline: list[TimelinePoint] = field(default_factory=list)
    last_correlation: CorrelationMatrix | None = None


class Pipeline:
    def __init__(self) -> None:
        self.state = PipelineState()
        self._tasks: list[asyncio.Task] = []
        self._stop = asyncio.Event()

    # ---- lifecycle ----------------------------------------------------

    async def start(self) -> None:
        loop = asyncio.get_running_loop()
        self._stop.clear()
        bus = self.state.bus
        bus.subscribe("logs", "storage")
        bus.subscribe("logs", "drain")
        self._sub_storage = bus._topics["logs"][0]
        self._sub_drain = bus._topics["logs"][1]
        self._tasks = [
            loop.create_task(self._producer_loop(),  name="producer"),
            loop.create_task(self._storage_loop(),   name="storage"),
            loop.create_task(self._drain_loop(),     name="drain"),
            loop.create_task(self._detector_loop(),  name="detector"),
            loop.create_task(self._prune_loop(),     name="pruner"),
            loop.create_task(self._correlation_loop(), name="corr"),
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

    # ---- control ------------------------------------------------------

    def inject_scenario(self, name: str) -> bool:
        sc = self.state.generator.inject(name)
        return sc is not None

    def list_scenarios(self) -> list[str]:
        return self.state.generator.scenario_catalog()

    def active_scenarios(self) -> list[str]:
        return self.state.generator.active_scenarios()

    # ---- producer + consumers ----------------------------------------

    async def _producer_loop(self) -> None:
        gen = self.state.generator
        bus = self.state.bus
        tick_period = 0.2
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

    # ---- detection tick ----------------------------------------------

    async def _detector_loop(self) -> None:
        period = settings.detector_period_seconds
        while not self._stop.is_set():
            await asyncio.sleep(period)
            try:
                self._run_detection_once()
            except Exception as e:
                print(f"[detector] error: {e}")

    def _run_detection_once(self) -> None:
        storage = self.state.storage
        aggs = storage.service_rates(settings.window_seconds)
        if not aggs:
            return
        pairs = storage.trace_service_pairs(window_seconds=settings.window_seconds)
        self.state.graph.observe(pairs)
        self.state.graph.update_node_metrics(aggs, settings.window_seconds)
        for a in aggs:
            self.state.forecaster.update(a["service"], a["error_rate"])
        new_anoms: list[Anomaly] = []
        new_anoms.extend(self.state.detector.detect_rates(aggs))
        svcs, mat = storage.feature_matrix(settings.window_seconds)
        new_anoms.extend(self.state.detector.detect_features(svcs, mat))
        fresh_templates = self.state.drain.drain_new_templates()
        new_anoms.extend(self.state.detector.detect_templates(
            fresh_templates, self.state.template_service,
        ))
        new_anoms.extend(self.state.rules.evaluate(aggs, settings.window_seconds))
        for a in new_anoms:
            order, hops = self.state.graph.blast_radius(
                a.service, settings.blast_radius_depth,
            )
            a.blast_radius = order
            a.blast_hops = hops
        if new_anoms:
            self.state.incidents.ingest(new_anoms, self.state.graph)
            for a in new_anoms:
                self.state.anomalies.append(a)
        timeline = storage.timeline(settings.window_seconds, buckets=60)
        self.state.last_timeline = timeline
        total = sum(p.total for p in timeline)
        errs = sum(p.errors for p in timeline)
        now = time.time()
        anoms_last_min = sum(1 for a in self.state.anomalies if (now - a.ts) <= 60.0)
        self.state.last_kpi = Kpi(
            logs_per_sec=round(total / max(1, settings.window_seconds), 2),
            error_rate=round(errs / max(1, total), 4),
            active_services=sum(1 for a in aggs if a["total"] > 0),
            anomalies_last_min=anoms_last_min,
            templates_tracked=self.state.drain.total_templates(),
            active_incidents=self.state.incidents.count_active(),
            window_seconds=settings.window_seconds,
            uptime_seconds=round(now - self.state.start_ts, 1),
        )

    async def _prune_loop(self) -> None:
        while not self._stop.is_set():
            await asyncio.sleep(10.0)
            self.state.storage.prune(settings.window_seconds * 4)

    async def _correlation_loop(self) -> None:
        while not self._stop.is_set():
            await asyncio.sleep(3.0)
            try:
                self.state.last_correlation = self._compute_correlation()
            except Exception as e:
                print(f"[correlation] error: {e}")

    def _compute_correlation(self) -> CorrelationMatrix:
        services, rates = self.state.storage.error_rate_matrix(settings.window_seconds)
        if not services:
            return CorrelationMatrix(
                services=[], matrix=[], window_seconds=settings.window_seconds, ts=time.time()
            )
        arr = np.array(rates, dtype=float)
        if arr.shape[1] < 3:
            n = len(services)
            eye = [[1.0 if i == j else 0.0 for j in range(n)] for i in range(n)]
            return CorrelationMatrix(
                services=services, matrix=eye,
                window_seconds=settings.window_seconds, ts=time.time(),
            )
        std = arr.std(axis=1)
        arr_centered = arr - arr.mean(axis=1, keepdims=True)
        std_safe = np.where(std < 1e-9, 1.0, std)
        normed = arr_centered / std_safe[:, None]
        n = arr.shape[1]
        corr = (normed @ normed.T) / n
        corr = np.nan_to_num(corr, nan=0.0, posinf=0.0, neginf=0.0)
        corr = np.clip(corr, -1.0, 1.0)
        for i, s in enumerate(std):
            if s < 1e-9:
                corr[i, :] = 0.0
                corr[:, i] = 0.0
                corr[i, i] = 1.0
        return CorrelationMatrix(
            services=services,
            matrix=corr.round(3).tolist(),
            window_seconds=settings.window_seconds,
            ts=time.time(),
        )

    # ---- snapshot for WS push ----------------------------------------

    def snapshot(self) -> StreamMessage:
        storage = self.state.storage
        recent_logs = storage.recent_records(limit=60)
        graph_snap = self.state.graph.snapshot()
        kpi = self.state.last_kpi or Kpi(
            logs_per_sec=0.0, error_rate=0.0, active_services=0,
            anomalies_last_min=0, templates_tracked=0, active_incidents=0,
            window_seconds=settings.window_seconds,
            uptime_seconds=round(time.time() - self.state.start_ts, 1),
        )
        return StreamMessage(
            kind="tick",
            kpi=kpi,
            logs=recent_logs,
            anomalies=list(self.state.anomalies)[-30:],
            incidents=self.state.incidents.active(limit=15),
            graph=graph_snap,
            timeline=self.state.last_timeline or storage.timeline(settings.window_seconds, 60),
            rules=self.state.rules.list(),
            active_scenarios=self.state.generator.active_scenarios(),
        )

    # ---- deep-dive helpers --------------------------------------------

    def get_trace(self, trace_id: str) -> Trace | None:
        records = self.state.storage.get_trace(trace_id)
        if not records:
            return None
        services_seen: dict[str, int] = {}
        spans: list[TraceSpan] = []
        for r in records:
            depth = services_seen.get(r.parent_service or "__root__", 0)
            if r.service not in services_seen:
                services_seen[r.service] = depth + 1
            spans.append(TraceSpan(
                ts=r.ts, service=r.service, parent_service=r.parent_service,
                level=r.level, latency_ms=r.latency_ms, status_code=r.status_code,
                message=r.message, span_id=r.span_id, depth=depth,
            ))
        started = min(s.ts for s in spans)
        ended = max(s.ts + s.latency_ms / 1000.0 for s in spans)
        duration = (ended - started) * 1000.0
        services = sorted({s.service for s in spans})
        has_errors = any(s.level in ("ERROR", "FATAL") for s in spans)
        return Trace(
            trace_id=trace_id, started=started, duration_ms=round(duration, 2),
            services=services, has_errors=has_errors, spans=spans,
        )

    def recent_trace_ids(self, limit: int = 30, errors_only: bool = False) -> list[str]:
        return self.state.storage.recent_trace_ids(
            limit=limit, window_seconds=settings.window_seconds, errors_only=errors_only,
        )

    def get_service_detail(self, service: str) -> ServiceDetail | None:
        storage = self.state.storage
        aggs = {a["service"]: a for a in storage.service_rates(settings.window_seconds)}
        if service not in aggs:
            return None
        a = aggs[service]
        snap = self.state.graph.snapshot()
        upstream: list[ServiceEdge] = [e for e in snap.edges if e.target == service]
        downstream: list[ServiceEdge] = [e for e in snap.edges if e.source == service]
        series = storage.service_latency_timeseries(service, settings.window_seconds)
        templates = storage.top_templates_for_service(service, settings.window_seconds)
        errors = storage.recent_errors_for_service(service)
        mu, sigma = self.state.forecaster.forecast(service)
        window_minutes = max(settings.window_seconds / 60.0, 1e-6)
        return ServiceDetail(
            id=service,
            group=GROUPS.get(service, "other"),
            logs_per_min=round(a["total"] / window_minutes, 2),
            error_rate=round(a["error_rate"], 4),
            mean_latency_ms=round(a["mean_lat"], 2),
            p95_latency_ms=round(a["p95_lat"], 2),
            health=round(max(0.0, 1.0 - a["error_rate"] * 1.8 - min(a["p95_lat"] / 800.0, 0.6)), 3),
            upstream=upstream,
            downstream=downstream,
            latency_series=series,
            top_templates=templates,
            recent_errors=errors,
            forecast_error_rate=round(mu, 4),
            forecast_stddev=round(sigma, 4),
        )

    def get_templates(
        self, limit: int = 80, service: str | None = None, level: str | None = None,
    ) -> list[TemplateInfo]:
        return self.state.storage.template_aggregates(
            settings.window_seconds, limit=limit, service=service, level=level,
        )

    def search_logs(
        self, query: str, service: str | None = None, level: str | None = None,
        limit: int = 50,
    ) -> SearchResult:
        hits, total = self.state.storage.search(
            query=query or "", service=service, level=level,
            window_seconds=settings.window_seconds, limit=limit,
        )
        return SearchResult(
            query=query or "",
            hits=hits,
            total_scanned=total,
            window_seconds=settings.window_seconds,
        )

    def correlation(self) -> CorrelationMatrix:
        return self.state.last_correlation or CorrelationMatrix(
            services=[], matrix=[], window_seconds=settings.window_seconds, ts=time.time(),
        )

    def list_incidents(self) -> list[Incident]:
        return self.state.incidents.all()

    # ---- rules --------------------------------------------------------

    def list_rules(self) -> list[AlertRule]:
        return self.state.rules.list()

    def add_rule(self, **kwargs) -> AlertRule:
        return self.state.rules.add(**kwargs)

    def delete_rule(self, rid: str) -> bool:
        return self.state.rules.delete(rid)

    def toggle_rule(self, rid: str, enabled: bool) -> AlertRule | None:
        return self.state.rules.toggle(rid, enabled)

    # ---- prometheus export -------------------------------------------

    def prometheus(self) -> str:
        kpi = self.state.last_kpi
        lines = [
            "# HELP logflow_logs_per_sec Current per-window logs/sec.",
            "# TYPE logflow_logs_per_sec gauge",
            f"logflow_logs_per_sec {kpi.logs_per_sec if kpi else 0}",
            "# HELP logflow_error_rate Current per-window error rate.",
            "# TYPE logflow_error_rate gauge",
            f"logflow_error_rate {kpi.error_rate if kpi else 0}",
            "# HELP logflow_active_incidents Count of active incidents.",
            "# TYPE logflow_active_incidents gauge",
            f"logflow_active_incidents {kpi.active_incidents if kpi else 0}",
            "# HELP logflow_templates_tracked Drain templates tracked.",
            "# TYPE logflow_templates_tracked gauge",
            f"logflow_templates_tracked {kpi.templates_tracked if kpi else 0}",
            "# HELP logflow_total_inserted Total logs inserted into DuckDB.",
            "# TYPE logflow_total_inserted counter",
            f"logflow_total_inserted {self.state.storage.total_inserted()}",
        ]
        aggs = self.state.storage.service_rates(settings.window_seconds)
        lines.append("# HELP logflow_service_logs_total Total logs per service in current window.")
        lines.append("# TYPE logflow_service_logs_total gauge")
        for a in aggs:
            lines.append(f'logflow_service_logs_total{{service="{a["service"]}"}} {a["total"]}')
        lines.append("# HELP logflow_service_error_rate Error rate per service in current window.")
        lines.append("# TYPE logflow_service_error_rate gauge")
        for a in aggs:
            lines.append(f'logflow_service_error_rate{{service="{a["service"]}"}} {a["error_rate"]:.4f}')
        lines.append("# HELP logflow_service_p95_latency_ms p95 latency per service (ms).")
        lines.append("# TYPE logflow_service_p95_latency_ms gauge")
        for a in aggs:
            lines.append(f'logflow_service_p95_latency_ms{{service="{a["service"]}"}} {a["p95_lat"]:.2f}')
        return "\n".join(lines) + "\n"
