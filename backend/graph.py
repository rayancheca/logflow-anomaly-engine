"""Service dependency graph and blast-radius computation.

The graph is built incrementally from the *observed* parent→service edges of
each log record. No topology config is required — the graph just materializes
from live traffic. Every tick we decay old edges so the graph reflects the
current behavior rather than lifetime history.

Blast-radius is a BFS traversal from an anomalous service through the
weighted directed edges, bounded by `max_depth`. Hop distances are returned
so the UI can draw concentric pulse rings.
"""
from __future__ import annotations

import time
from collections import defaultdict, deque
from dataclasses import dataclass, field

from .generator import GROUPS  # default group labels for known services
from .schemas import ServiceEdge, ServiceGraphSnapshot, ServiceNode


@dataclass
class EdgeState:
    weight: float = 0.0
    last_seen: float = 0.0


@dataclass
class NodeState:
    id: str
    logs_per_min: float = 0.0
    error_rate: float = 0.0
    mean_latency_ms: float = 0.0
    health: float = 1.0


class ServiceGraph:
    def __init__(self, decay: float = 0.92) -> None:
        self.edges: dict[tuple[str, str], EdgeState] = defaultdict(EdgeState)
        self.nodes: dict[str, NodeState] = {}
        self.decay = decay

    def observe(self, pairs: list[tuple[str, str]]) -> None:
        now = time.time()
        # Apply decay to existing edges
        for state in self.edges.values():
            state.weight *= self.decay
        for parent, child in pairs:
            if not parent or not child or parent == child:
                continue
            key = (parent, child)
            es = self.edges[key]
            es.weight += 1.0
            es.last_seen = now
            self.nodes.setdefault(parent, NodeState(id=parent))
            self.nodes.setdefault(child, NodeState(id=child))
        # prune trivially small edges
        stale = [k for k, v in self.edges.items() if v.weight < 0.3]
        for k in stale:
            self.edges.pop(k, None)

    def update_node_metrics(self, aggs: list[dict], window_seconds: int) -> None:
        window_minutes = max(window_seconds / 60.0, 1e-6)
        for a in aggs:
            svc = a["service"]
            n = self.nodes.setdefault(svc, NodeState(id=svc))
            n.logs_per_min = a["total"] / window_minutes
            n.error_rate = a["error_rate"]
            n.mean_latency_ms = a["mean_lat"]
            # Simple composite health score
            n.health = max(
                0.0,
                1.0 - a["error_rate"] * 1.8 - min(a["p95_lat"] / 800.0, 0.6),
            )

    def snapshot(self) -> ServiceGraphSnapshot:
        nodes: list[ServiceNode] = []
        for n in self.nodes.values():
            nodes.append(ServiceNode(
                id=n.id,
                group=GROUPS.get(n.id, "other"),
                logs_per_min=round(n.logs_per_min, 2),
                error_rate=round(n.error_rate, 4),
                mean_latency_ms=round(n.mean_latency_ms, 2),
                health=round(n.health, 3),
            ))
        # Normalise edges to 0..1 for rendering
        if self.edges:
            max_w = max(e.weight for e in self.edges.values())
        else:
            max_w = 1.0
        edges: list[ServiceEdge] = [
            ServiceEdge(source=s, target=t, weight=round(es.weight / max_w, 3))
            for (s, t), es in self.edges.items()
        ]
        return ServiceGraphSnapshot(nodes=nodes, edges=edges)

    def blast_radius(self, source: str, max_depth: int = 4) -> tuple[list[str], dict[str, int]]:
        """BFS forward traversal returning impacted services and hop distances."""
        if source not in self.nodes:
            return [source], {source: 0}
        adj: dict[str, list[tuple[str, float]]] = defaultdict(list)
        for (s, t), es in self.edges.items():
            adj[s].append((t, es.weight))
        seen: dict[str, int] = {source: 0}
        q: deque[str] = deque([source])
        while q:
            node = q.popleft()
            depth = seen[node]
            if depth >= max_depth:
                continue
            for nb, w in adj.get(node, []):
                if w < 0.1:
                    continue
                if nb not in seen:
                    seen[nb] = depth + 1
                    q.append(nb)
        order = sorted(seen.keys(), key=lambda k: (seen[k], k))
        return order, seen
