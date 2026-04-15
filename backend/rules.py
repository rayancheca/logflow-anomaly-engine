"""User-defined alert-rules engine.

A rule is a threshold check with dwell time: "fire when `metric` `op`
`threshold` for at least `duration_s` seconds on `service` (or `*`)".
Rules emit anomalies of kind `rule_fired` which are fed through the same
incident engine as every other signal.
"""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass

from .schemas import AlertRule, Anomaly, RuleMetric, RuleOp


@dataclass
class _RuleEval:
    rule: AlertRule
    entered_at: float | None = None
    firing: bool = False


class RulesEngine:
    def __init__(self) -> None:
        self._rules: dict[str, _RuleEval] = {}
        self._install_defaults()

    def _install_defaults(self) -> None:
        defaults: list[AlertRule] = [
            AlertRule(
                id="r_err_any", name="Error rate > 8% on any service",
                service="*", metric="error_rate", op=">",
                threshold=0.08, duration_s=4.0,
            ),
            AlertRule(
                id="r_pay_p95", name="payments p95 > 400ms",
                service="payments", metric="p95_latency", op=">",
                threshold=400.0, duration_s=4.0,
            ),
            AlertRule(
                id="r_ntf_flood", name="notifications > 500 logs/min",
                service="notifications", metric="logs_per_min", op=">",
                threshold=500.0, duration_s=4.0,
            ),
        ]
        for r in defaults:
            self._rules[r.id] = _RuleEval(rule=r)

    # ---- CRUD ---------------------------------------------------------

    def list(self) -> list[AlertRule]:
        return [e.rule for e in self._rules.values()]

    def get(self, rid: str) -> AlertRule | None:
        e = self._rules.get(rid)
        return e.rule if e else None

    def add(
        self, name: str, service: str, metric: RuleMetric, op: RuleOp,
        threshold: float, duration_s: float = 5.0,
    ) -> AlertRule:
        rid = f"r_{uuid.uuid4().hex[:6]}"
        rule = AlertRule(
            id=rid, name=name, service=service, metric=metric, op=op,
            threshold=threshold, duration_s=duration_s,
        )
        self._rules[rid] = _RuleEval(rule=rule)
        return rule

    def delete(self, rid: str) -> bool:
        return self._rules.pop(rid, None) is not None

    def toggle(self, rid: str, enabled: bool) -> AlertRule | None:
        e = self._rules.get(rid)
        if not e:
            return None
        e.rule.enabled = enabled
        if not enabled:
            e.entered_at = None
            e.firing = False
        return e.rule

    # ---- evaluation ---------------------------------------------------

    def evaluate(self, aggs: list[dict], window_seconds: int) -> list[Anomaly]:
        """Check every enabled rule against per-service aggregates."""
        now = time.time()
        fired: list[Anomaly] = []
        per_svc: dict[str, dict] = {a["service"]: a for a in aggs}
        window_minutes = max(window_seconds / 60.0, 1e-6)
        for ev in self._rules.values():
            if not ev.rule.enabled:
                ev.entered_at = None
                ev.firing = False
                continue
            if ev.rule.service == "*":
                targets = list(per_svc.values())
            elif ev.rule.service in per_svc:
                targets = [per_svc[ev.rule.service]]
            else:
                ev.entered_at = None
                ev.firing = False
                continue
            match_svc: str | None = None
            match_val: float = 0.0
            for m in targets:
                val = self._metric_value(m, ev.rule.metric, window_minutes)
                if self._cmp(val, ev.rule.op, ev.rule.threshold):
                    match_svc = m["service"]
                    match_val = val
                    break
            if match_svc is not None:
                if ev.entered_at is None:
                    ev.entered_at = now
                dwell = now - ev.entered_at
                if dwell >= ev.rule.duration_s and not ev.firing:
                    ev.firing = True
                    ev.rule.fired_count += 1
                    ev.rule.last_fired = now
                    fired.append(Anomaly(
                        id=f"rule_{ev.rule.id}_{int(now * 1000)}",
                        ts=now,
                        kind="rule_fired",
                        service=match_svc,
                        severity=min(0.95, 0.55 + (ev.rule.fired_count * 0.05)),
                        description=(
                            f"rule · {ev.rule.name} "
                            f"(observed {self._fmt_val(ev.rule.metric, match_val)})"
                        ),
                    ))
            else:
                ev.entered_at = None
                ev.firing = False
        return fired

    # ---- helpers ------------------------------------------------------

    @staticmethod
    def _metric_value(agg: dict, metric: RuleMetric, window_minutes: float) -> float:
        if metric == "error_rate":
            return float(agg.get("error_rate", 0.0))
        if metric == "p95_latency":
            return float(agg.get("p95_lat", 0.0))
        if metric == "logs_per_min":
            return float(agg.get("total", 0.0)) / window_minutes
        return 0.0

    @staticmethod
    def _cmp(val: float, op: RuleOp, threshold: float) -> bool:
        if op == ">":
            return val > threshold
        if op == "<":
            return val < threshold
        if op == ">=":
            return val >= threshold
        if op == "<=":
            return val <= threshold
        return False

    @staticmethod
    def _fmt_val(metric: RuleMetric, val: float) -> str:
        if metric == "error_rate":
            return f"{val * 100:.1f}%"
        if metric == "p95_latency":
            return f"{val:.0f}ms"
        return f"{val:.0f}/min"
