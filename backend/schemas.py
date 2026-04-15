"""Pydantic schemas for all wire formats used across the pipeline."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Severity = Literal["DEBUG", "INFO", "WARN", "ERROR", "FATAL"]
AnomalyKind = Literal["rate_spike", "feature_outlier", "new_template", "rule_fired"]
IncidentState = Literal["active", "resolving", "resolved"]
RuleMetric = Literal["error_rate", "p95_latency", "logs_per_min"]
RuleOp = Literal[">", "<", ">=", "<="]


# ---- logs & traces --------------------------------------------------------

class LogRecord(BaseModel):
    """A single structured log line."""
    ts: float = Field(..., description="Unix timestamp (seconds, float).")
    service: str
    level: Severity
    trace_id: str
    span_id: str
    parent_service: str | None = None
    latency_ms: float = 0.0
    status_code: int = 200
    message: str
    template_id: int | None = None


class TraceSpan(BaseModel):
    ts: float
    service: str
    parent_service: str | None
    level: Severity
    latency_ms: float
    status_code: int
    message: str
    span_id: str
    depth: int = 0


class Trace(BaseModel):
    trace_id: str
    started: float
    duration_ms: float
    services: list[str]
    has_errors: bool
    spans: list[TraceSpan]


# ---- anomalies ------------------------------------------------------------

class Anomaly(BaseModel):
    id: str
    ts: float
    kind: AnomalyKind
    service: str
    severity: float = Field(..., description="Normalized 0..1 anomaly severity.")
    description: str
    blast_radius: list[str] = Field(default_factory=list)
    blast_hops: dict[str, int] = Field(default_factory=dict)
    incident_id: str | None = None


# ---- incidents ------------------------------------------------------------

class Incident(BaseModel):
    id: str
    started: float
    last_ts: float
    state: IncidentState
    severity: float
    root_service: str
    suspected_cause: str
    services: list[str]
    impact: list[str]
    impact_hops: dict[str, int]
    anomaly_ids: list[str]
    anomaly_kinds: list[AnomalyKind]
    title: str
    anomaly_count: int = 0


# ---- rules ----------------------------------------------------------------

class AlertRule(BaseModel):
    id: str
    name: str
    service: str
    metric: RuleMetric
    op: RuleOp
    threshold: float
    duration_s: float = 5.0
    enabled: bool = True
    fired_count: int = 0
    last_fired: float | None = None


class RuleCreate(BaseModel):
    name: str
    service: str = "*"
    metric: RuleMetric
    op: RuleOp
    threshold: float
    duration_s: float = 5.0


# ---- service graph --------------------------------------------------------

class ServiceNode(BaseModel):
    id: str
    group: str
    logs_per_min: float = 0.0
    error_rate: float = 0.0
    mean_latency_ms: float = 0.0
    health: float = 1.0


class ServiceEdge(BaseModel):
    source: str
    target: str
    weight: float


class ServiceGraphSnapshot(BaseModel):
    nodes: list[ServiceNode]
    edges: list[ServiceEdge]


# ---- service detail -------------------------------------------------------

class ServiceLatencyPoint(BaseModel):
    ts: float
    p50: float
    p95: float
    p99: float
    mean: float


class TemplateInfo(BaseModel):
    template_id: int
    template: str
    count: int
    service: str | None = None
    level: Severity | None = None
    first_seen: float | None = None
    last_seen: float | None = None


class ServiceDetail(BaseModel):
    id: str
    group: str
    logs_per_min: float
    error_rate: float
    mean_latency_ms: float
    p95_latency_ms: float
    health: float
    upstream: list[ServiceEdge]
    downstream: list[ServiceEdge]
    latency_series: list[ServiceLatencyPoint]
    top_templates: list[TemplateInfo]
    recent_errors: list[LogRecord]
    forecast_error_rate: float
    forecast_stddev: float


# ---- kpi / timeline / search / correlations -------------------------------

class Kpi(BaseModel):
    logs_per_sec: float
    error_rate: float
    active_services: int
    anomalies_last_min: int
    templates_tracked: int
    active_incidents: int
    window_seconds: int
    uptime_seconds: float


class TimelinePoint(BaseModel):
    ts: float
    total: int
    errors: int
    warns: int


class SearchHit(BaseModel):
    ts: float
    service: str
    level: Severity
    message: str
    trace_id: str
    latency_ms: float


class SearchResult(BaseModel):
    query: str
    hits: list[SearchHit]
    total_scanned: int
    window_seconds: int


class CorrelationMatrix(BaseModel):
    services: list[str]
    matrix: list[list[float]]
    window_seconds: int
    ts: float


class StreamMessage(BaseModel):
    kind: Literal["tick"]
    kpi: Kpi
    logs: list[LogRecord]
    anomalies: list[Anomaly]
    incidents: list[Incident]
    graph: ServiceGraphSnapshot
    timeline: list[TimelinePoint]
    rules: list[AlertRule]
    active_scenarios: list[str]
