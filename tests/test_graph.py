"""Tests for the ServiceGraph dependency graph and blast-radius BFS."""
import pytest
from backend.graph import ServiceGraph


class TestServiceGraphObserve:
    def test_observe_creates_nodes(self) -> None:
        g = ServiceGraph()
        g.observe([("gateway", "payments")])
        assert "gateway" in g.nodes
        assert "payments" in g.nodes

    def test_observe_creates_edge(self) -> None:
        g = ServiceGraph()
        g.observe([("gateway", "payments")])
        assert ("gateway", "payments") in g.edges

    def test_observe_ignores_self_loops(self) -> None:
        g = ServiceGraph()
        g.observe([("payments", "payments")])
        assert ("payments", "payments") not in g.edges

    def test_observe_ignores_empty_strings(self) -> None:
        g = ServiceGraph()
        g.observe([("", "payments"), ("gateway", "")])
        assert not g.nodes

    def test_observe_accumulates_weight(self) -> None:
        g = ServiceGraph(decay=1.0)  # no decay
        g.observe([("a", "b")])
        w1 = g.edges[("a", "b")].weight
        g.observe([("a", "b")])
        w2 = g.edges[("a", "b")].weight
        assert w2 > w1

    def test_observe_applies_decay(self) -> None:
        g = ServiceGraph(decay=0.5)
        g.observe([("a", "b")])
        w1 = g.edges[("a", "b")].weight
        g.observe([])  # no new edges, but decay fires
        w2 = g.edges[("a", "b")].weight
        assert w2 < w1

    def test_stale_edges_pruned(self) -> None:
        g = ServiceGraph(decay=0.01)
        g.observe([("a", "b")])
        for _ in range(30):
            g.observe([])
        assert ("a", "b") not in g.edges


class TestServiceGraphBlastRadius:
    def _build(self) -> ServiceGraph:
        g = ServiceGraph(decay=1.0)
        # payments → ledger → analytics
        for _ in range(5):
            g.observe([("payments", "ledger"), ("ledger", "analytics")])
        return g

    def test_source_always_included(self) -> None:
        g = self._build()
        order, hops = g.blast_radius("payments")
        assert "payments" in order
        assert hops["payments"] == 0

    def test_direct_downstream_at_depth_1(self) -> None:
        g = self._build()
        _, hops = g.blast_radius("payments")
        assert hops.get("ledger") == 1

    def test_two_hop_downstream(self) -> None:
        g = self._build()
        _, hops = g.blast_radius("payments")
        assert hops.get("analytics") == 2

    def test_max_depth_respected(self) -> None:
        g = ServiceGraph(decay=1.0)
        for _ in range(5):
            g.observe([("a", "b"), ("b", "c"), ("c", "d"), ("d", "e")])
        _, hops = g.blast_radius("a", max_depth=2)
        assert "d" not in hops
        assert "e" not in hops

    def test_unknown_source_returns_self_only(self) -> None:
        g = ServiceGraph()
        order, hops = g.blast_radius("nonexistent")
        assert order == ["nonexistent"]
        assert hops == {"nonexistent": 0}

    def test_order_by_hop_depth(self) -> None:
        g = self._build()
        order, hops = g.blast_radius("payments")
        depths = [hops[s] for s in order]
        assert depths == sorted(depths)


class TestServiceGraphSnapshot:
    def test_snapshot_includes_nodes_and_edges(self) -> None:
        g = ServiceGraph(decay=1.0)
        for _ in range(3):
            g.observe([("a", "b")])
        snap = g.snapshot()
        ids = {n.id for n in snap.nodes}
        assert "a" in ids
        assert "b" in ids
        assert len(snap.edges) == 1

    def test_edge_weights_normalised_to_one(self) -> None:
        g = ServiceGraph(decay=1.0)
        for _ in range(5):
            g.observe([("a", "b"), ("a", "c")])
        snap = g.snapshot()
        weights = [e.weight for e in snap.edges]
        assert max(weights) <= 1.0

    def test_empty_graph_snapshot(self) -> None:
        g = ServiceGraph()
        snap = g.snapshot()
        assert snap.nodes == []
        assert snap.edges == []


class TestUpdateNodeMetrics:
    def test_metrics_applied_to_node(self) -> None:
        g = ServiceGraph()
        g.nodes["payments"] = __import__("backend.graph", fromlist=["NodeState"]).NodeState(id="payments")
        aggs = [{"service": "payments", "total": 600, "error_rate": 0.05,
                 "mean_lat": 120.0, "p95_lat": 200.0}]
        g.update_node_metrics(aggs, window_seconds=60)
        n = g.nodes["payments"]
        assert n.logs_per_min == pytest.approx(600.0)  # 600 total / 1 minute
        assert n.error_rate == pytest.approx(0.05)

    def test_high_error_rate_reduces_health(self) -> None:
        g = ServiceGraph()
        g.nodes["payments"] = __import__("backend.graph", fromlist=["NodeState"]).NodeState(id="payments")
        aggs = [{"service": "payments", "total": 100, "error_rate": 0.50,
                 "mean_lat": 100.0, "p95_lat": 800.0}]
        g.update_node_metrics(aggs, window_seconds=60)
        assert g.nodes["payments"].health <= 0.0
