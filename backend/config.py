"""Tunable constants for the LogFlow Anomaly Engine."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    # Ingestion rate (logs per second at steady state).
    base_rate: float = 60.0
    burst_rate: float = 220.0

    # Rolling window used for detection, in seconds.
    window_seconds: int = 60

    # How often the detector loop fires.
    detector_period_seconds: float = 2.0

    # How often the pipeline emits a KPI snapshot to the UI.
    stats_period_seconds: float = 1.0

    # Z-score threshold for the rate detector.
    zscore_threshold: float = 3.0

    # IsolationForest contamination parameter.
    iforest_contamination: float = 0.06

    # Maximum rows kept in the in-memory ring for the live feed.
    feed_buffer: int = 400

    # DuckDB file (":memory:" keeps everything in RAM).
    duckdb_path: str = ":memory:"

    # Blast-radius BFS depth limit.
    blast_radius_depth: int = 4

    # WebSocket broadcast coalescing period.
    ws_period_seconds: float = 0.4


settings = Settings()
