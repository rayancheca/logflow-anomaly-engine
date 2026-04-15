"""Three-layer anomaly detector.

Layer 1 — rate-based.  Maintains a rolling Z-score per service on error-rate
          and log volume and fires when the current value is N standard
          deviations above baseline.

Layer 2 — feature-based.  Trains an IsolationForest on recent per-service
          feature vectors and flags the services whose decision score falls
          below the contamination threshold.

Layer 3 — structural.  Any new Drain template that appears more than k times
          inside the current window is flagged.

All three feed into a single deduplicating anomaly bus. Each anomaly carries
its detection kind, severity, and the triggering service — the pipeline then
attaches a blast-radius afterwards.
"""
from __future__ import annotations

import math
import time
import uuid
from collections import defaultdict, deque
from dataclasses import dataclass, field

import numpy as np
from sklearn.ensemble import IsolationForest

from .schemas import Anomaly


@dataclass
class RollingStat:
    values: deque[float] = field(default_factory=lambda: deque(maxlen=60))

    def update(self, v: float) -> float:
        self.values.append(v)
        return self.zscore(v)

    def zscore(self, v: float) -> float:
        if len(self.values) < 8:
            return 0.0
        arr = np.array(self.values, dtype=float)
        mu = float(arr.mean())
        sd = float(arr.std())
        if sd < 1e-6:
            return 0.0
        return (v - mu) / sd


class AnomalyDetector:
    def __init__(self, zscore_threshold: float, contamination: float, warmup_seconds: float = 25.0) -> None:
        self.zscore_threshold = zscore_threshold
        self.contamination = contamination
        self.warmup_seconds = warmup_seconds
        self._started_at = time.time()
        self._rate_stats: dict[str, RollingStat] = defaultdict(RollingStat)
        self._error_stats: dict[str, RollingStat] = defaultdict(RollingStat)
        self._latency_stats: dict[str, RollingStat] = defaultdict(RollingStat)
        self._recent_anomalies: deque[Anomaly] = deque(maxlen=50)
        self._template_firsts: dict[int, float] = {}
        self._seen_template_ids: set[int] = set()

    # ---- Layer 1 ---- rate-based
    def detect_rates(self, aggs: list[dict]) -> list[Anomaly]:
        out: list[Anomaly] = []
        now = time.time()
        for a in aggs:
            svc = a["service"]
            total = float(a["total"])
            err = float(a["errors"])
            lat = float(a["p95_lat"])
            z_total = self._rate_stats[svc].update(total)
            z_err = self._error_stats[svc].update(err)
            z_lat = self._latency_stats[svc].update(lat)
            # Error-rate spike
            if z_err >= self.zscore_threshold and err >= 3:
                out.append(self._mk(
                    kind="rate_spike", service=svc,
                    severity=self._normalize_z(z_err),
                    description=f"error burst: {int(err)} errors, z={z_err:.1f}",
                ))
            # Latency spike combined with volume
            if z_lat >= self.zscore_threshold and lat > 100:
                out.append(self._mk(
                    kind="rate_spike", service=svc,
                    severity=self._normalize_z(z_lat),
                    description=f"p95 latency jump to {lat:.0f}ms, z={z_lat:.1f}",
                ))
            # Pure volume spike
            if z_total >= self.zscore_threshold + 1.0 and total > 20:
                out.append(self._mk(
                    kind="rate_spike", service=svc,
                    severity=self._normalize_z(z_total),
                    description=f"log volume spike: {int(total)} logs, z={z_total:.1f}",
                ))
        return out

    # ---- Layer 2 ---- feature-based
    def detect_features(self, services: list[str], matrix: list[list[float]]) -> list[Anomaly]:
        if len(matrix) < 6:
            return []
        X = np.array(matrix, dtype=float)
        # Log-transform counts so heavy-tailed fields don't dominate
        X = np.log1p(X)
        model = IsolationForest(
            n_estimators=80,
            contamination=self.contamination,
            random_state=42,
        )
        try:
            model.fit(X)
            preds = model.predict(X)            # -1 = outlier
            scores = model.decision_function(X) # lower = more anomalous
        except Exception:
            return []
        out: list[Anomaly] = []
        for svc, pred, score in zip(services, preds, scores):
            if pred == -1:
                sev = max(0.0, min(1.0, 0.5 - score))
                out.append(self._mk(
                    kind="feature_outlier", service=svc, severity=sev,
                    description=f"multi-feature outlier (iforest score={score:+.2f})",
                ))
        return out

    # ---- Layer 3 ---- structural
    def detect_templates(self, new_templates: list[tuple[int, str]], service_hint: dict[int, str]) -> list[Anomaly]:
        out: list[Anomaly] = []
        now = time.time()
        for tid, text in new_templates:
            if tid in self._seen_template_ids:
                continue
            self._seen_template_ids.add(tid)
            # Suppress during warmup — every template is "new" at boot
            if (now - self._started_at) < self.warmup_seconds:
                continue
            svc = service_hint.get(tid, "unknown")
            if svc == "unknown":
                continue
            out.append(self._mk(
                kind="new_template", service=svc, severity=0.6,
                description=f"new log template: \"{text[:70]}\"",
            ))
        return out

    # ---- utilities ----
    def recent(self) -> list[Anomaly]:
        return list(self._recent_anomalies)

    def _normalize_z(self, z: float) -> float:
        return max(0.0, min(1.0, (z - self.zscore_threshold) / 6.0 + 0.5))

    def _mk(self, *, kind, service, severity, description) -> Anomaly:
        a = Anomaly(
            id=uuid.uuid4().hex[:10],
            ts=time.time(),
            kind=kind,
            service=service,
            severity=float(severity),
            description=description,
        )
        self._recent_anomalies.append(a)
        return a
