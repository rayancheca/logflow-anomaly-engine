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

from .schemas import (
    LogRecord,
    SearchHit,
    ServiceLatencyPoint,
    TemplateInfo,
    TimelinePoint,
)


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
CREATE INDEX IF NOT EXISTS idx_logs_ts       ON logs(ts);
CREATE INDEX IF NOT EXISTS idx_logs_service  ON logs(service);
CREATE INDEX IF NOT EXISTS idx_logs_trace    ON logs(trace_id);
CREATE INDEX IF NOT EXISTS idx_logs_template ON logs(template_id);
"""


class Storage:
    def __init__(self, path: str = ":memory:") -> None:
        self._conn = duckdb.connect(path)
        self._conn.execute(SCHEMA)
        self._lock = threading.Lock()
        self.recent: deque[LogRecord] = deque(maxlen=1200)
        self._total_inserted = 0

    # ---- writes -------------------------------------------------------

    def insert_many(self, records: Iterable[LogRecord]) -> int:
        rows = [
            (
                r.ts, r.service, r.level, r.trace_id, r.span_id,
                r.parent_service, r.latency_ms, r.status_code, r.message,
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

    # ---- reads: live feed & aggregates --------------------------------

    def recent_records(self, limit: int = 200) -> list[LogRecord]:
        return list(self.recent)[-limit:]

    def service_rates(self, window_seconds: int) -> list[dict]:
        cutoff = time.time() - window_seconds
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT
                    service,
                    COUNT(*)                                                AS total,
                    SUM(CASE WHEN level IN ('ERROR','FATAL') THEN 1 ELSE 0 END) AS errors,
                    SUM(CASE WHEN level = 'WARN' THEN 1 ELSE 0 END)         AS warns,
                    AVG(latency_ms)                                         AS mean_lat,
                    QUANTILE_CONT(latency_ms, 0.5)                          AS p50_lat,
                    QUANTILE_CONT(latency_ms, 0.95)                         AS p95_lat,
                    QUANTILE_CONT(latency_ms, 0.99)                         AS p99_lat
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
                "p50_lat": float(r[5] or 0.0),
                "p95_lat": float(r[6] or 0.0),
                "p99_lat": float(r[7] or 0.0),
                "error_rate": (r[2] / r[1]) if r[1] else 0.0,
            }
            for r in rows
        ]

    def timeline(self, window_seconds: int, buckets: int = 60) -> list[TimelinePoint]:
        now = time.time()
        end_sec = int(now) + 1
        start_sec = end_sec - buckets
        start = float(start_sec)
        with self._lock:
            rows = self._conn.execute(
                """
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
            sec = start_sec + i
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

    # ---- reads: trace retrieval --------------------------------------

    def get_trace(self, trace_id: str) -> list[LogRecord]:
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT ts, service, level, trace_id, span_id, parent_service,
                       latency_ms, status_code, message, template_id
                FROM logs
                WHERE trace_id = ?
                ORDER BY ts
                """,
                [trace_id],
            ).fetchall()
        return [
            LogRecord(
                ts=r[0], service=r[1], level=r[2], trace_id=r[3], span_id=r[4],
                parent_service=r[5], latency_ms=r[6], status_code=r[7],
                message=r[8], template_id=r[9],
            )
            for r in rows
        ]

    def recent_trace_ids(self, limit: int = 30, window_seconds: int = 60,
                         errors_only: bool = False) -> list[str]:
        cutoff = time.time() - window_seconds
        where = "ts >= ?"
        args: list = [cutoff]
        if errors_only:
            where += " AND level IN ('ERROR', 'FATAL')"
        with self._lock:
            rows = self._conn.execute(
                f"""
                SELECT trace_id, MAX(ts) AS latest
                FROM logs
                WHERE {where}
                GROUP BY trace_id
                ORDER BY latest DESC
                LIMIT ?
                """,
                args + [limit],
            ).fetchall()
        return [r[0] for r in rows]

    # ---- reads: search -----------------------------------------------

    def search(
        self, query: str, service: str | None, level: str | None,
        window_seconds: int, limit: int = 50,
    ) -> tuple[list[SearchHit], int]:
        cutoff = time.time() - window_seconds
        where = ["ts >= ?"]
        args: list = [cutoff]
        if query:
            where.append("message ILIKE ?")
            args.append(f"%{query}%")
        if service and service != "*":
            where.append("service = ?")
            args.append(service)
        if level and level != "*":
            where.append("level = ?")
            args.append(level)
        with self._lock:
            total = self._conn.execute(
                f"SELECT COUNT(*) FROM logs WHERE {' AND '.join(where)}",
                args,
            ).fetchone()[0]
            rows = self._conn.execute(
                f"""
                SELECT ts, service, level, message, trace_id, latency_ms
                FROM logs
                WHERE {' AND '.join(where)}
                ORDER BY ts DESC
                LIMIT ?
                """,
                args + [limit],
            ).fetchall()
        hits = [
            SearchHit(
                ts=r[0], service=r[1], level=r[2],
                message=r[3], trace_id=r[4], latency_ms=r[5],
            )
            for r in rows
        ]
        return hits, int(total)

    # ---- reads: per-service detail -----------------------------------

    def service_latency_timeseries(
        self, service: str, window_seconds: int, buckets: int = 60,
    ) -> list[ServiceLatencyPoint]:
        now = time.time()
        end_sec = int(now) + 1
        start_sec = end_sec - buckets
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT
                    CAST(FLOOR(ts) AS BIGINT) AS sec,
                    QUANTILE_CONT(latency_ms, 0.5),
                    QUANTILE_CONT(latency_ms, 0.95),
                    QUANTILE_CONT(latency_ms, 0.99),
                    AVG(latency_ms)
                FROM logs
                WHERE service = ? AND ts >= ?
                GROUP BY sec
                ORDER BY sec
                """,
                [service, float(start_sec)],
            ).fetchall()
        by_sec: dict[int, tuple[float, float, float, float]] = {
            int(r[0]): (float(r[1] or 0), float(r[2] or 0), float(r[3] or 0), float(r[4] or 0))
            for r in rows
        }
        out: list[ServiceLatencyPoint] = []
        for i in range(buckets):
            sec = start_sec + i
            p50, p95, p99, mean = by_sec.get(sec, (0.0, 0.0, 0.0, 0.0))
            out.append(ServiceLatencyPoint(
                ts=float(sec), p50=p50, p95=p95, p99=p99, mean=mean,
            ))
        return out

    def top_templates_for_service(
        self, service: str, window_seconds: int, limit: int = 8,
    ) -> list[TemplateInfo]:
        cutoff = time.time() - window_seconds
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT template_id, MAX(level), COUNT(*),
                       MIN(ts), MAX(ts), ANY_VALUE(message)
                FROM logs
                WHERE service = ? AND ts >= ? AND template_id IS NOT NULL
                GROUP BY template_id
                ORDER BY COUNT(*) DESC
                LIMIT ?
                """,
                [service, cutoff, limit],
            ).fetchall()
        return [
            TemplateInfo(
                template_id=int(r[0]),
                template=str(r[5]),
                count=int(r[2]),
                service=service,
                level=r[1],
                first_seen=float(r[3]),
                last_seen=float(r[4]),
            )
            for r in rows
        ]

    def recent_errors_for_service(
        self, service: str, limit: int = 10, window_seconds: int = 120,
    ) -> list[LogRecord]:
        cutoff = time.time() - window_seconds
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT ts, service, level, trace_id, span_id, parent_service,
                       latency_ms, status_code, message, template_id
                FROM logs
                WHERE service = ? AND ts >= ? AND level IN ('ERROR','FATAL','WARN')
                ORDER BY ts DESC
                LIMIT ?
                """,
                [service, cutoff, limit],
            ).fetchall()
        return [
            LogRecord(
                ts=r[0], service=r[1], level=r[2], trace_id=r[3], span_id=r[4],
                parent_service=r[5], latency_ms=r[6], status_code=r[7],
                message=r[8], template_id=r[9],
            )
            for r in rows
        ]

    # ---- reads: templates catalog ------------------------------------

    def template_aggregates(
        self, window_seconds: int, limit: int = 80, service: str | None = None,
        level: str | None = None,
    ) -> list[TemplateInfo]:
        cutoff = time.time() - window_seconds
        where = ["ts >= ?", "template_id IS NOT NULL"]
        args: list = [cutoff]
        if service and service != "*":
            where.append("service = ?")
            args.append(service)
        if level and level != "*":
            where.append("level = ?")
            args.append(level)
        with self._lock:
            rows = self._conn.execute(
                f"""
                SELECT template_id,
                       ANY_VALUE(service),
                       MAX(level),
                       COUNT(*)                      AS n,
                       MIN(ts), MAX(ts),
                       ANY_VALUE(message)
                FROM logs
                WHERE {' AND '.join(where)}
                GROUP BY template_id
                ORDER BY n DESC
                LIMIT ?
                """,
                args + [limit],
            ).fetchall()
        return [
            TemplateInfo(
                template_id=int(r[0]),
                template=str(r[6]),
                count=int(r[3]),
                service=r[1],
                level=r[2],
                first_seen=float(r[4]),
                last_seen=float(r[5]),
            )
            for r in rows
        ]

    # ---- reads: error-rate correlation matrix ------------------------

    def error_rate_matrix(
        self, window_seconds: int,
    ) -> tuple[list[str], list[list[float]]]:
        """Return per-service per-second error counts as [service][sec] rows."""
        now = time.time()
        end_sec = int(now) + 1
        start_sec = end_sec - window_seconds
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT service,
                       CAST(FLOOR(ts) AS BIGINT) AS sec,
                       COUNT(*),
                       SUM(CASE WHEN level IN ('ERROR','FATAL','WARN') THEN 1 ELSE 0 END)
                FROM logs
                WHERE ts >= ?
                GROUP BY service, sec
                """,
                [float(start_sec)],
            ).fetchall()
        services = sorted({r[0] for r in rows})
        index = {s: i for i, s in enumerate(services)}
        n = window_seconds
        mat: list[list[float]] = [[0.0] * n for _ in services]
        for svc, sec, total, errs in rows:
            col = int(sec) - start_sec
            if 0 <= col < n:
                rate = (float(errs) / float(total)) if total else 0.0
                mat[index[svc]][col] = rate
        return services, mat
