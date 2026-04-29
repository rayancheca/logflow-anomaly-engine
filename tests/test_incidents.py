"""Tests for the IncidentEngine correlation and root-cause ranking."""
import time
import uuid
import pytest
from backend.graph import ServiceGraph
from backend.incidents import IncidentEngine
from backend.schemas import Anomaly


def _anomaly(service: str = "payments", severity: float = 0.7,
             blast: list[str] | None = None, hops: dict[str, int] | None = None) -> Anomaly:
    br = blast or [service]
    return Anomaly(
        id=f"a_{uuid.uuid4().hex[:6]}",
        ts=time.time(),
        kind="rate_spike",
        service=service,
        severity=severity,
        description=f"{service} anomaly",
        blast_radius=br,
        blast_hops=hops or {service: 0},
    )


def _graph_with_edges(edges: list[tuple[str, str]], repeats: int = 5) -> ServiceGraph:
    g = ServiceGraph(decay=1.0)
    for _ in range(repeats):
        g.observe(edges)
    return g


class TestIncidentEngineCreate:
    def test_single_anomaly_creates_incident(self) -> None:
        engine = IncidentEngine()
        g = ServiceGraph()
        a = _anomaly("payments")
        engine.ingest([a], g)
        assert engine.count_active() == 1

    def test_anomaly_gets_incident_id(self) -> None:
        engine = IncidentEngine()
        g = ServiceGraph()
        a = _anomaly("payments")
        engine.ingest([a], g)
        assert a.incident_id is not None


class TestIncidentEngineMerge:
    def test_same_service_anomalies_merge(self) -> None:
        engine = IncidentEngine(correlation_window=30.0)
        g = ServiceGraph()
        a1 = _anomaly("payments")
        a2 = _anomaly("payments")
        engine.ingest([a1, a2], g)
        assert engine.count_active() == 1

    def test_graph_adjacent_services_merge(self) -> None:
        engine = IncidentEngine(correlation_window=30.0)
        g = _graph_with_edges([("payments", "checkout")])
        # payments anomaly with checkout in blast radius
        a1 = _anomaly("payments", blast=["payments", "checkout"],
                       hops={"payments": 0, "checkout": 1})
        a2 = _anomaly("checkout")
        engine.ingest([a1, a2], g)
        assert engine.count_active() == 1

    def test_unrelated_services_create_separate_incidents(self) -> None:
        engine = IncidentEngine(correlation_window=30.0)
        g = ServiceGraph()
        a1 = _anomaly("payments")
        a2 = _anomaly("catalog")
        engine.ingest([a1, a2], g)
        assert engine.count_active() == 2

    def test_severity_escalates_on_merge(self) -> None:
        engine = IncidentEngine(correlation_window=30.0)
        g = ServiceGraph()
        a1 = _anomaly("payments", severity=0.5)
        a2 = _anomaly("payments", severity=0.9)
        engine.ingest([a1, a2], g)
        incidents = engine.active()
        assert incidents[0].severity == pytest.approx(0.9, abs=0.01)


class TestIncidentEngineRootCause:
    def test_root_cause_identified_for_multi_service(self) -> None:
        engine = IncidentEngine(correlation_window=60.0)
        # payments → checkout → cart topology
        g = _graph_with_edges([("payments", "checkout"), ("checkout", "cart")])
        a_pay = _anomaly("payments",
                         blast=["payments", "checkout", "cart"],
                         hops={"payments": 0, "checkout": 1, "cart": 2})
        a_chk = _anomaly("checkout",
                         blast=["checkout", "cart"],
                         hops={"checkout": 0, "cart": 1})
        engine.ingest([a_pay, a_chk], g)
        incidents = engine.active()
        assert len(incidents) == 1
        # payments should rank as root since checkout blast covers it
        assert incidents[0].root_service in {"payments", "checkout"}


class TestIncidentEngineStateTransitions:
    def test_incident_resolves_after_window(self) -> None:
        engine = IncidentEngine(resolve_after=0.0, close_after=0.01)
        g = ServiceGraph()
        a = _anomaly("payments")
        a.ts = time.time() - 1.0  # 1 second old
        engine.ingest([a], g)
        incidents = engine.all()
        states = {i.state for i in incidents}
        assert states & {"resolving", "resolved"}

    def test_count_active_excludes_resolved(self) -> None:
        engine = IncidentEngine(resolve_after=0.0, close_after=0.0)
        g = ServiceGraph()
        a = _anomaly("payments")
        a.ts = time.time() - 1000.0
        engine.ingest([a], g)
        assert engine.count_active() == 0


class TestIncidentEngineQueries:
    def test_active_respects_limit(self) -> None:
        engine = IncidentEngine()
        g = ServiceGraph()
        svcs = [f"svc_{i}" for i in range(25)]
        for svc in svcs:
            engine.ingest([_anomaly(svc)], g)
        assert len(engine.active(limit=10)) == 10

    def test_all_returns_all_incidents(self) -> None:
        engine = IncidentEngine()
        g = ServiceGraph()
        for svc in ["a", "b", "c"]:
            engine.ingest([_anomaly(svc)], g)
        assert len(engine.all()) == 3
