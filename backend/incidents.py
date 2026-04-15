"""Incident correlation engine.

Anomalies are raw signals. Incidents are stories. This engine clusters
anomalies by temporal proximity + service-graph proximity and ranks a root
cause per incident — so the UI can show "payments outage impacting 6
services" instead of 14 unconnected alerts.

Correlation rules
-----------------
Two anomalies belong to the same incident iff:
  * they fire within `correlation_window` seconds of each other, and
  * their services are graph-adjacent — either one's service is in the
    other's blast radius, or one's blast radius intersects the other's
    current impact set.

Root-cause ranking
------------------
For each incident, we pick the member service whose forward blast radius
covers the most *other* member services, tie-breaking by smallest total
hop distance. That is: the service that best explains the others as
downstream effects.

State machine
-------------
An incident is `active` while it is still receiving new anomalies. If no
new anomaly lands for `resolve_after` seconds it enters `resolving`, and
after `close_after` seconds it becomes `resolved` and drops out of the
active list.
"""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field

from .graph import ServiceGraph
from .schemas import Anomaly, AnomalyKind, Incident, IncidentState


@dataclass
class _IncState:
    id: str
    started: float
    last_ts: float
    anomaly_ids: list[str]
    anomaly_kinds: list[AnomalyKind]
    services: set[str]
    impact: set[str]
    impact_hops: dict[str, int]
    max_severity: float
    root_service: str
    suspected_cause: str
    state: IncidentState
    title: str

    def to_schema(self) -> Incident:
        return Incident(
            id=self.id,
            started=self.started,
            last_ts=self.last_ts,
            state=self.state,
            severity=round(self.max_severity, 3),
            root_service=self.root_service,
            suspected_cause=self.suspected_cause,
            services=sorted(self.services),
            impact=sorted(self.impact, key=lambda s: (self.impact_hops.get(s, 99), s)),
            impact_hops=dict(self.impact_hops),
            anomaly_ids=list(self.anomaly_ids)[-50:],
            anomaly_kinds=list(self.anomaly_kinds)[-50:],
            title=self.title,
            anomaly_count=len(self.anomaly_ids),
        )


class IncidentEngine:
    def __init__(
        self,
        correlation_window: float = 25.0,
        resolve_after: float = 18.0,
        close_after: float = 45.0,
    ) -> None:
        self.correlation_window = correlation_window
        self.resolve_after = resolve_after
        self.close_after = close_after
        self._incidents: dict[str, _IncState] = {}

    # ---- ingestion ----------------------------------------------------

    def ingest(self, anomalies: list[Anomaly], graph: ServiceGraph) -> None:
        for a in anomalies:
            match = self._find_match(a)
            if match is not None:
                self._merge(match, a)
                a.incident_id = match.id
            else:
                inc = self._create(a)
                a.incident_id = inc.id
        self._refresh_states()
        self._rank_roots(graph)

    def _find_match(self, a: Anomaly) -> _IncState | None:
        best: _IncState | None = None
        best_score = -1.0
        for inc in self._incidents.values():
            if inc.state == "resolved":
                continue
            dt = a.ts - inc.last_ts
            if dt > self.correlation_window:
                continue
            score = 0.0
            if a.service in inc.impact:
                score += 3.0
            if a.service in inc.services:
                score += 4.0
            if any(s in a.blast_radius for s in inc.services):
                score += 2.0
            if score <= 0:
                continue
            recency = max(0.0, 1.0 - dt / self.correlation_window)
            score += recency
            if score > best_score:
                best_score = score
                best = inc
        return best

    def _create(self, a: Anomaly) -> _IncState:
        iid = f"inc_{uuid.uuid4().hex[:8]}"
        inc = _IncState(
            id=iid,
            started=a.ts,
            last_ts=a.ts,
            anomaly_ids=[a.id],
            anomaly_kinds=[a.kind],
            services={a.service},
            impact=set(a.blast_radius),
            impact_hops=dict(a.blast_hops),
            max_severity=a.severity,
            root_service=a.service,
            suspected_cause=a.description,
            state="active",
            title=self._title_for(a),
        )
        self._incidents[iid] = inc
        return inc

    def _merge(self, inc: _IncState, a: Anomaly) -> None:
        inc.last_ts = max(inc.last_ts, a.ts)
        inc.anomaly_ids.append(a.id)
        inc.anomaly_kinds.append(a.kind)
        inc.services.add(a.service)
        for s in a.blast_radius:
            inc.impact.add(s)
            h = a.blast_hops.get(s, 99)
            inc.impact_hops[s] = min(inc.impact_hops.get(s, 99), h)
        if a.severity > inc.max_severity:
            inc.max_severity = a.severity
            inc.suspected_cause = a.description
        inc.state = "active"

    # ---- state + ranking ----------------------------------------------

    def _refresh_states(self) -> None:
        now = time.time()
        drops: list[str] = []
        for inc in self._incidents.values():
            since = now - inc.last_ts
            if since > self.close_after + 300:
                drops.append(inc.id)
                continue
            if since > self.close_after:
                inc.state = "resolved"
            elif since > self.resolve_after:
                inc.state = "resolving"
            else:
                inc.state = "active"
        for d in drops:
            self._incidents.pop(d, None)

    def _rank_roots(self, graph: ServiceGraph) -> None:
        """Pick the root service per incident.

        Failures propagate from callee → caller: when a leaf service breaks,
        every upstream caller that depends on it also starts erroring. So the
        *root cause* is the most-downstream service — the one that the
        largest number of other members can reach via forward blast radius.
        """
        for inc in self._incidents.values():
            if len(inc.services) <= 1:
                inc.root_service = next(iter(inc.services))
                inc.title = f"{inc.root_service} · {self._summarise_kinds(inc.anomaly_kinds)}"
                continue
            members = list(inc.services)
            hop_cache: dict[str, dict[str, int]] = {}
            for s in members:
                _, h = graph.blast_radius(s, max_depth=5)
                hop_cache[s] = h
            best_svc = inc.root_service
            best_score = -1e9
            for svc in members:
                reached_by = sum(
                    1 for other in members
                    if other != svc and svc in hop_cache[other]
                )
                avg_depth = 0.0
                if reached_by:
                    avg_depth = sum(
                        hop_cache[other].get(svc, 99)
                        for other in members if other != svc and svc in hop_cache[other]
                    ) / reached_by
                # More reachers + deeper average depth wins
                score = reached_by * 100.0 + avg_depth
                if score > best_score:
                    best_score = score
                    best_svc = svc
            inc.root_service = best_svc
            inc.title = f"{best_svc} incident · {len(inc.services)} services"

    @staticmethod
    def _summarise_kinds(kinds: list[AnomalyKind]) -> str:
        tally: dict[str, int] = {}
        for k in kinds:
            tally[k] = tally.get(k, 0) + 1
        return ", ".join(f"{k.replace('_', ' ')}×{v}" for k, v in tally.items())

    def _title_for(self, a: Anomaly) -> str:
        return f"{a.service} · {a.kind.replace('_', ' ')}"

    # ---- public reads -------------------------------------------------

    def active(self, limit: int = 20) -> list[Incident]:
        items = [inc for inc in self._incidents.values() if inc.state != "resolved"]
        items.sort(key=lambda i: (i.max_severity, i.last_ts), reverse=True)
        return [i.to_schema() for i in items[:limit]]

    def all(self) -> list[Incident]:
        items = sorted(self._incidents.values(), key=lambda i: i.last_ts, reverse=True)
        return [i.to_schema() for i in items]

    def count_active(self) -> int:
        return sum(1 for inc in self._incidents.values() if inc.state != "resolved")
