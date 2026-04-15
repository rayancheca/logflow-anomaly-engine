"""Pydantic schemas for all wire formats used across the pipeline."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Severity = Literal["DEBUG", "INFO", "WARN", "ERROR", "FATAL"]
AnomalyKind = Literal["rate_spike", "feature_outlier", "new_template"]


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


class Anomaly(BaseModel):
    id: str
    ts: float
    kind: AnomalyKind
    service: str
    severity: float = Field(..., description="Normalized 0..1 anomaly severity.")
    description: str
    blast_radius: list[str] = Field(default_factory=list)
    blast_hops: dict[str, int] = Field(default_factory=dict)


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


class Kpi(BaseModel):
    logs_per_sec: float
    error_rate: float
    active_services: int
    anomalies_last_min: int
    templates_tracked: int
    window_seconds: int
    uptime_seconds: float


class TimelinePoint(BaseModel):
    ts: float
    total: int
    errors: int
    warns: int


class StreamMessage(BaseModel):
    kind: Literal["tick"]
    kpi: Kpi
    logs: list[LogRecord]
    anomalies: list[Anomaly]
    graph: ServiceGraphSnapshot
    timeline: list[TimelinePoint]
