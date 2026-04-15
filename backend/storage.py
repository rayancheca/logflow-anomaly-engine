"""DuckDB-backed columnar storage for log analytics.

DuckDB gives us a columnar OLAP engine with near-ClickHouse performance but
embedded — zero infra, same SQL idioms. Everything is kept in an in-memory
database by default so the demo is ephemeral.
"""
from __future__ import annotations

import threading
import time
from collections import deque
from typing import Iterable

import duckdb

from .schemas import LogRecord, TimelinePoint


SCHEMA = """
CREATE TABLE IF NOT EXISTS logs (
    ts DOUBLE,
    service VARCHAR,
    level VARCHAR,
    trace_id VARCHAR,
    span_id VARCHAR,
    parent_service VARCHAR,
    latency_ms DOUBLE,
    status_code INTEGER,
    message VARCHAR,
    template_id INTEGER
);
CREATE INDEX IF NOT EXISTS idx_logs_ts ON logs(ts);
CREATE INDEX IF NOT EXISTS idx_logs_service ON logs(service);
"""


class Storage:
    def __init__(self, path: str = ":memory:") -> None:
        self._conn = duckdb.connect(path)
        self._conn.execute(SCHEMA)
        self._lock = threading.Lock()
        # Ring buffer of most recent records for the live feed (avoids a full
        # scan on every WebSocket tick).
        self.recent: deque[LogRecord] = deque(maxlen=800)
        self._total_inserted = 0

    def insert_many(self, records: Iterable[LogRecord]) -> int:
        rows = [
            (
                r.ts,
                r.service,
                r.level,
                r.trace_id,
                r.span_id,
                r.parent_service,
                r.latency_ms,
                r.status_code,
                r.message,
                r.template_id,
            )
            for r in records
        ]
        if not rows:
            return 0
        with self._lock:
            self._conn.executemany(
                "INSERT INTO logs VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                rows,
            )
            self._total_inserted += len(rows)
            for r in records:
                self.recent.append(r)
        return len(rows)

    def prune(self, keep_seconds: int) -> int:
        cutoff = time.time() - keep_seconds
        with self._lock:
            n = self._conn.execute(
                "DELETE FROM logs WHERE ts < ?", [cutoff]
            ).fetchone()
        return n[0] if n else 0

    def recent_records(self, limit: int = 200) -> list[LogRecord]:
        # Pull from the ring buffer for speed.
        return list(self.recent)[-limit:]

    def service_rates(self, window_seconds: int) -> list[dict]:
        """Return per-service aggregates for the last N seconds."""
        cutoff = time.time() - window_seconds
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT
                    service,
                    COUNT(*)                                        AS total,
                    SUM(CASE WHEN level IN ('ERROR','FATAL') THEN 1 ELSE 0 END) AS errors,
                    SUM(CASE WHEN level = 'WARN'                  THEN 1 ELSE 0 END) AS warns,
                    AVG(latency_ms)                                 AS mean_lat,
                    QUANTILE_CONT(latency_ms, 0.95)                 AS p95_lat
                FROM logs
                WHERE ts >= ?
                GROUP BY service
                ORDER BY total DESC
                """,
                [cutoff],
            ).fetchall()
        return [
            {
                "service": r[0],
                "total": r[1],
                "errors": r[2],
                "warns": r[3],
                "mean_lat": float(r[4] or 0.0),
                "p95_lat": float(r[5] or 0.0),
                "error_rate": (r[2] / r[1]) if r[1] else 0.0,
            }
            for r in rows
        ]

    def timeline(self, window_seconds: int, buckets: int = 60) -> list[TimelinePoint]:
        """Return per-second histogram of total/error/warn counts."""
        now = time.time()
        start = now - window_seconds
        with self._lock:
            rows = self._conn.execute(
                f"""
                SELECT
                    CAST(FLOOR(ts) AS BIGINT) AS sec,
                    COUNT(*),
                    SUM(CASE WHEN level IN ('ERROR','FATAL') THEN 1 ELSE 0 END),
                    SUM(CASE WHEN level = 'WARN' THEN 1 ELSE 0 END)
                FROM logs
                WHERE ts >= ?
                GROUP BY sec
                ORDER BY sec
                """,
                [start],
            ).fetchall()
        by_sec = {int(r[0]): (r[1], r[2], r[3]) for r in rows}
        out: list[TimelinePoint] = []
        for i in range(buckets):
            sec = int(start) + i
            t = by_sec.get(sec, (0, 0, 0))
            out.append(TimelinePoint(ts=float(sec), total=t[0], errors=t[1], warns=t[2]))
        return out

    def trace_service_pairs(self, window_seconds: int) -> list[tuple[str, str]]:
        cutoff = time.time() - window_seconds
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT parent_service, service
                FROM logs
                WHERE ts >= ? AND parent_service IS NOT NULL
                """,
                [cutoff],
            ).fetchall()
        return [(r[0], r[1]) for r in rows]

    def feature_matrix(self, window_seconds: int) -> tuple[list[str], list[list[float]]]:
        """Return per-service feature rows for IsolationForest."""
        aggs = self.service_rates(window_seconds)
        services = [a["service"] for a in aggs]
        matrix = [
            [
                float(a["total"]),
                float(a["errors"]),
                float(a["warns"]),
                float(a["mean_lat"]),
                float(a["p95_lat"]),
                float(a["error_rate"]),
            ]
            for a in aggs
        ]
        return services, matrix

    def total_inserted(self) -> int:
        return self._total_inserted
