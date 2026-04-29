"""Tests for the alert-rules engine."""
import time
import pytest
from backend.rules import RulesEngine


def _agg(service: str = "payments", error_rate: float = 0.0, p95_lat: float = 100.0,
         total: int = 100) -> dict:
    return {
        "service": service,
        "error_rate": error_rate,
        "p95_lat": p95_lat,
        "mean_lat": 50.0,
        "total": total,
    }


class TestRulesEngineCRUD:
    def test_list_returns_defaults(self) -> None:
        engine = RulesEngine()
        rules = engine.list()
        assert len(rules) == 3
        ids = {r.id for r in rules}
        assert "r_err_any" in ids

    def test_add_creates_new_rule(self) -> None:
        engine = RulesEngine()
        rule = engine.add(
            name="custom",
            service="catalog",
            metric="error_rate",
            op=">",
            threshold=0.15,
        )
        assert engine.get(rule.id) is not None
        assert len(engine.list()) == 4

    def test_delete_removes_rule(self) -> None:
        engine = RulesEngine()
        rule = engine.add("temp", "*", "error_rate", ">", 0.5)
        result = engine.delete(rule.id)
        assert result is True
        assert engine.get(rule.id) is None

    def test_delete_nonexistent_returns_false(self) -> None:
        engine = RulesEngine()
        assert engine.delete("nope") is False

    def test_toggle_disables_rule(self) -> None:
        engine = RulesEngine()
        updated = engine.toggle("r_err_any", False)
        assert updated is not None
        assert updated.enabled is False

    def test_toggle_enables_rule(self) -> None:
        engine = RulesEngine()
        engine.toggle("r_err_any", False)
        updated = engine.toggle("r_err_any", True)
        assert updated is not None
        assert updated.enabled is True

    def test_toggle_nonexistent_returns_none(self) -> None:
        engine = RulesEngine()
        assert engine.toggle("no_such_rule", True) is None

    def test_get_returns_none_for_missing(self) -> None:
        engine = RulesEngine()
        assert engine.get("missing") is None


class TestRulesEngineEvaluate:
    def test_no_fire_when_below_threshold(self) -> None:
        engine = RulesEngine()
        aggs = [_agg("payments", error_rate=0.01)]
        fired = engine.evaluate(aggs, window_seconds=60)
        assert fired == []

    def test_fires_after_dwell(self) -> None:
        engine = RulesEngine()
        engine.delete("r_pay_p95")
        engine.delete("r_ntf_flood")
        rule = engine.add("fast fire", "*", "error_rate", ">", 0.05, duration_s=0.0)

        aggs = [_agg("payments", error_rate=0.10)]
        fired = engine.evaluate(aggs, window_seconds=60)
        assert any(a.service == "payments" for a in fired)

    def test_does_not_fire_before_dwell(self) -> None:
        engine = RulesEngine()
        for r in engine.list():
            if r.id != "r_err_any":
                engine.delete(r.id)
        # Override duration so it can't fire immediately
        engine.delete("r_err_any")
        rule = engine.add("slow fire", "*", "error_rate", ">", 0.05, duration_s=9999.0)
        aggs = [_agg("payments", error_rate=0.20)]
        fired = engine.evaluate(aggs, window_seconds=60)
        assert fired == []

    def test_fires_only_once_per_threshold_breach(self) -> None:
        engine = RulesEngine()
        for r in engine.list():
            engine.delete(r.id)
        engine.add("once", "*", "error_rate", ">", 0.05, duration_s=0.0)
        aggs = [_agg("payments", error_rate=0.20)]
        fired1 = engine.evaluate(aggs, window_seconds=60)
        fired2 = engine.evaluate(aggs, window_seconds=60)
        assert len(fired1) == 1
        assert len(fired2) == 0

    def test_resets_after_condition_clears(self) -> None:
        engine = RulesEngine()
        for r in engine.list():
            engine.delete(r.id)
        engine.add("reset", "*", "error_rate", ">", 0.05, duration_s=0.0)
        high = [_agg("payments", error_rate=0.20)]
        low = [_agg("payments", error_rate=0.01)]
        engine.evaluate(high, window_seconds=60)  # fires
        engine.evaluate(low, window_seconds=60)   # resets
        fired = engine.evaluate(high, window_seconds=60)  # should fire again
        assert len(fired) == 1

    def test_wildcard_service_matches_any(self) -> None:
        engine = RulesEngine()
        for r in engine.list():
            engine.delete(r.id)
        engine.add("any svc", "*", "error_rate", ">", 0.05, duration_s=0.0)
        aggs = [_agg("catalog", error_rate=0.30)]
        fired = engine.evaluate(aggs, window_seconds=60)
        assert any(a.service == "catalog" for a in fired)

    def test_specific_service_ignores_others(self) -> None:
        engine = RulesEngine()
        for r in engine.list():
            engine.delete(r.id)
        engine.add("payments only", "payments", "error_rate", ">", 0.05, duration_s=0.0)
        aggs = [_agg("catalog", error_rate=0.99)]
        fired = engine.evaluate(aggs, window_seconds=60)
        assert fired == []

    def test_disabled_rule_never_fires(self) -> None:
        engine = RulesEngine()
        for r in engine.list():
            engine.delete(r.id)
        rule = engine.add("disabled", "*", "error_rate", ">", 0.0, duration_s=0.0)
        engine.toggle(rule.id, False)
        aggs = [_agg("payments", error_rate=0.99)]
        fired = engine.evaluate(aggs, window_seconds=60)
        assert fired == []

    def test_p95_latency_metric(self) -> None:
        engine = RulesEngine()
        for r in engine.list():
            engine.delete(r.id)
        engine.add("lat", "payments", "p95_latency", ">", 100.0, duration_s=0.0)
        aggs = [_agg("payments", p95_lat=500.0)]
        fired = engine.evaluate(aggs, window_seconds=60)
        assert len(fired) == 1

    def test_logs_per_min_metric(self) -> None:
        engine = RulesEngine()
        for r in engine.list():
            engine.delete(r.id)
        engine.add("flood", "notifications", "logs_per_min", ">", 10.0, duration_s=0.0)
        # 600 total in 60s window = 600 logs/min
        aggs = [_agg("notifications", total=600)]
        fired = engine.evaluate(aggs, window_seconds=60)
        assert len(fired) == 1
