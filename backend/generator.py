"""Synthetic log generator simulating a 12-service e-commerce platform.

The topology is a directed DAG: traffic enters at `gateway`, branches through
`auth`, `catalog`, `cart`, `checkout`, `payments`, `inventory`, `fulfillment`,
`notifications`, `search`, `recommendations`, and terminates at `analytics`.
Each generated trace walks a path through this DAG, emitting correlated log
lines per service with realistic latency and occasional errors.

Scenario injection lets the UI trigger controlled failure modes such as a
payments outage or catalog latency spike, so the detection + blast-radius
pipeline has something interesting to react to.
"""
from __future__ import annotations

import asyncio
import math
import random
import time
import uuid
from dataclasses import dataclass, field
from typing import Iterable

from .schemas import LogRecord, Severity

# Directed dependency edges. (caller, callee)
TOPOLOGY: dict[str, list[str]] = {
    "gateway":         ["auth", "catalog", "search"],
    "auth":            ["sessions"],
    "sessions":        [],
    "catalog":         ["inventory", "recommendations"],
    "search":          ["catalog"],
    "cart":            ["catalog", "sessions"],
    "checkout":        ["cart", "payments", "inventory"],
    "payments":        ["ledger"],
    "ledger":          [],
    "inventory":       [],
    "recommendations": [],
    "fulfillment":     ["inventory", "notifications"],
    "notifications":   [],
    "analytics":       [],
}

# Entry-point services that start traces (weighted).
ENTRY_POINTS: list[tuple[str, float]] = [
    ("gateway",  0.55),
    ("checkout", 0.20),
    ("cart",     0.10),
    ("fulfillment", 0.10),
    ("analytics", 0.05),
]

# Service groups for UI coloring.
GROUPS: dict[str, str] = {
    "gateway": "edge",
    "auth": "edge",
    "sessions": "core",
    "catalog": "core",
    "search": "edge",
    "cart": "core",
    "checkout": "commerce",
    "payments": "commerce",
    "ledger": "commerce",
    "inventory": "core",
    "recommendations": "core",
    "fulfillment": "commerce",
    "notifications": "delivery",
    "analytics": "delivery",
}


MESSAGE_TEMPLATES: dict[str, list[tuple[str, Severity, float]]] = {
    # template, level, base weight
    "gateway": [
        ("GET /api/v1/{route} handled in {lat}ms status={code}", "INFO", 0.85),
        ("rate limit near threshold client={client}", "WARN", 0.10),
        ("upstream timeout contacting {svc}", "ERROR", 0.05),
    ],
    "auth": [
        ("user authenticated uid={uid}", "INFO", 0.80),
        ("invalid credentials uid={uid}", "WARN", 0.15),
        ("token signing key rotated", "INFO", 0.05),
    ],
    "sessions": [
        ("session cache hit key={key}", "DEBUG", 0.60),
        ("session cache miss key={key}", "INFO", 0.35),
        ("redis latency degraded p99={lat}ms", "WARN", 0.05),
    ],
    "catalog": [
        ("product lookup sku={sku} hit=true", "INFO", 0.75),
        ("product lookup sku={sku} hit=false", "DEBUG", 0.20),
        ("postgres slow query plan_id={plan}", "WARN", 0.05),
    ],
    "search": [
        ("elastic query q={q} took={lat}ms", "INFO", 0.85),
        ("elastic circuit breaker half-open", "WARN", 0.10),
        ("index refresh failed shard={shard}", "ERROR", 0.05),
    ],
    "cart": [
        ("cart updated user={uid} items={n}", "INFO", 0.85),
        ("stale cart version merged user={uid}", "WARN", 0.10),
        ("cart persist failed user={uid}", "ERROR", 0.05),
    ],
    "checkout": [
        ("checkout session created id={id}", "INFO", 0.80),
        ("checkout retry attempt={attempt}", "WARN", 0.15),
        ("checkout aborted reason={reason}", "ERROR", 0.05),
    ],
    "payments": [
        ("charge authorized amount={amt} currency={cur}", "INFO", 0.85),
        ("charge declined reason={reason}", "WARN", 0.10),
        ("acquirer timeout region={region}", "ERROR", 0.05),
    ],
    "ledger": [
        ("ledger entry posted id={id}", "INFO", 0.90),
        ("ledger write replay id={id}", "WARN", 0.08),
        ("ledger consistency check failed", "ERROR", 0.02),
    ],
    "inventory": [
        ("stock decremented sku={sku} qty={qty}", "INFO", 0.80),
        ("stock oversold sku={sku}", "WARN", 0.15),
        ("inventory db lock contention", "ERROR", 0.05),
    ],
    "recommendations": [
        ("model inference uid={uid} took={lat}ms", "INFO", 0.90),
        ("recommendation cache rebuild started", "INFO", 0.08),
        ("model fallback triggered", "WARN", 0.02),
    ],
    "fulfillment": [
        ("shipment dispatched id={id} carrier={c}", "INFO", 0.85),
        ("shipment delayed id={id}", "WARN", 0.10),
        ("warehouse api unreachable", "ERROR", 0.05),
    ],
    "notifications": [
        ("email sent to user={uid}", "INFO", 0.80),
        ("push queue depth high depth={d}", "WARN", 0.15),
        ("sms gateway rejected code={code}", "ERROR", 0.05),
    ],
    "analytics": [
        ("event batch flushed size={n}", "INFO", 0.90),
        ("ingest backpressure applied", "WARN", 0.08),
        ("schema drift detected field={f}", "ERROR", 0.02),
    ],
}

LEVEL_STATUS = {"DEBUG": 200, "INFO": 200, "WARN": 206, "ERROR": 500, "FATAL": 503}


@dataclass
class Scenario:
    """Transient failure scenario that biases log output."""
    service: str
    level_override: Severity
    multiplier: float
    latency_mul: float
    ttl: float
    started: float = field(default_factory=time.time)

    def active(self, now: float) -> bool:
        return (now - self.started) < self.ttl


@dataclass
class Generator:
    rng: random.Random = field(default_factory=lambda: random.Random(1337))
    scenarios: list[Scenario] = field(default_factory=list)

    def list_services(self) -> list[str]:
        return list(TOPOLOGY.keys())

    def inject(self, kind: str) -> Scenario | None:
        """Inject a named failure scenario. Returns the scenario object."""
        kind = kind.lower()
        presets = {
            "payments_outage": Scenario(
                service="payments", level_override="ERROR",
                multiplier=4.0, latency_mul=5.0, ttl=30.0,
            ),
            "catalog_latency": Scenario(
                service="catalog", level_override="WARN",
                multiplier=2.5, latency_mul=8.0, ttl=25.0,
            ),
            "inventory_deadlock": Scenario(
                service="inventory", level_override="ERROR",
                multiplier=3.5, latency_mul=3.0, ttl=20.0,
            ),
            "notifications_flood": Scenario(
                service="notifications", level_override="WARN",
                multiplier=5.0, latency_mul=1.5, ttl=25.0,
            ),
            "search_index_fail": Scenario(
                service="search", level_override="ERROR",
                multiplier=3.0, latency_mul=4.0, ttl=20.0,
            ),
        }
        s = presets.get(kind)
        if not s:
            return None
        s.started = time.time()
        self.scenarios.append(s)
        return s

    def _prune(self, now: float) -> None:
        self.scenarios = [s for s in self.scenarios if s.active(now)]

    def _scenario_for(self, svc: str, now: float) -> Scenario | None:
        for s in self.scenarios:
            if s.active(now) and s.service == svc:
                return s
        return None

    def _pick_entry(self) -> str:
        r = self.rng.random()
        acc = 0.0
        for svc, w in ENTRY_POINTS:
            acc += w
            if r <= acc:
                return svc
        return ENTRY_POINTS[-1][0]

    def _walk(self, start: str, depth: int = 0, seen: set[str] | None = None) -> list[tuple[str, str | None]]:
        seen = seen or set()
        path: list[tuple[str, str | None]] = []
        stack: list[tuple[str, str | None, int]] = [(start, None, 0)]
        while stack:
            node, parent, d = stack.pop(0)
            if node in seen or d > 4:
                continue
            seen.add(node)
            path.append((node, parent))
            children = TOPOLOGY.get(node, [])
            # randomly skip some children to vary trace shape
            for c in children:
                if self.rng.random() < 0.72:
                    stack.append((c, node, d + 1))
        return path

    def _make_line(self, svc: str, level: Severity, now: float, lat: float) -> str:
        tmpls = MESSAGE_TEMPLATES[svc]
        # select by weight
        total = sum(w for _, lvl, w in tmpls if lvl == level) or 1.0
        roll = self.rng.random() * total
        chosen = tmpls[0][0]
        acc = 0.0
        for tmpl, lvl, w in tmpls:
            if lvl != level:
                continue
            acc += w
            if roll <= acc:
                chosen = tmpl
                break
        subs = {
            "route": self.rng.choice(["products", "cart", "checkout", "orders", "search"]),
            "code": str(self.rng.choice([200, 201, 204, 404, 500, 503])),
            "client": f"ip={self.rng.randint(1, 250)}.{self.rng.randint(1, 250)}",
            "svc": self.rng.choice(list(TOPOLOGY.keys())),
            "uid": f"u_{self.rng.randint(1000, 9999)}",
            "key": f"sess_{uuid.uuid4().hex[:8]}",
            "lat": f"{lat:.1f}",
            "sku": f"sku_{self.rng.randint(10000, 99999)}",
            "plan": f"p_{self.rng.randint(100, 999)}",
            "q": self.rng.choice(["sneakers", "laptop", "coffee", "chair", "cable"]),
            "shard": str(self.rng.randint(0, 11)),
            "n": str(self.rng.randint(1, 9)),
            "id": f"id_{uuid.uuid4().hex[:10]}",
            "attempt": str(self.rng.randint(1, 4)),
            "reason": self.rng.choice(["declined", "timeout", "fraud", "gateway_error"]),
            "amt": f"{self.rng.uniform(5, 900):.2f}",
            "cur": self.rng.choice(["USD", "EUR", "GBP"]),
            "region": self.rng.choice(["us-east", "eu-west", "ap-south"]),
            "qty": str(self.rng.randint(1, 6)),
            "c": self.rng.choice(["ups", "dhl", "fedex"]),
            "d": str(self.rng.randint(200, 9000)),
            "code": str(self.rng.choice([400, 429, 500])),
            "f": self.rng.choice(["user_id", "ts", "amount"]),
        }
        return chosen.format(**{k: subs.get(k, "?") for k in subs})

    def _pick_level(self, svc: str, now: float) -> tuple[Severity, float]:
        sc = self._scenario_for(svc, now)
        base_weights: list[tuple[Severity, float]] = []
        for _, lvl, w in MESSAGE_TEMPLATES[svc]:
            base_weights.append((lvl, w))
        if sc:
            # inflate the override level's weight
            base_weights = [
                (lvl, w * (sc.multiplier if lvl == sc.level_override else 1.0))
                for lvl, w in base_weights
            ]
        total = sum(w for _, w in base_weights)
        r = self.rng.random() * total
        acc = 0.0
        chosen: Severity = "INFO"
        for lvl, w in base_weights:
            acc += w
            if r <= acc:
                chosen = lvl
                break
        lat_base = {"DEBUG": 1.5, "INFO": 8.0, "WARN": 45.0, "ERROR": 180.0, "FATAL": 400.0}[chosen]
        jitter = self.rng.lognormvariate(0.0, 0.5)
        lat = lat_base * jitter
        if sc:
            lat *= sc.latency_mul
        return chosen, lat

    def tick(self, n: int, now: float | None = None) -> list[LogRecord]:
        """Emit up to N log records for this quantum."""
        now = now or time.time()
        self._prune(now)
        out: list[LogRecord] = []
        while len(out) < n:
            trace_id = uuid.uuid4().hex[:12]
            start = self._pick_entry()
            path = self._walk(start)
            for svc, parent in path:
                if len(out) >= n:
                    break
                level, lat = self._pick_level(svc, now)
                msg = self._make_line(svc, level, now, lat)
                out.append(LogRecord(
                    ts=now + self.rng.random() * 0.05,
                    service=svc,
                    level=level,
                    trace_id=trace_id,
                    span_id=uuid.uuid4().hex[:8],
                    parent_service=parent,
                    latency_ms=round(lat, 2),
                    status_code=LEVEL_STATUS[level],
                    message=msg,
                ))
        return out

    def scenario_catalog(self) -> list[str]:
        return [
            "payments_outage",
            "catalog_latency",
            "inventory_deadlock",
            "notifications_flood",
            "search_index_fail",
        ]


async def run_generator(bus, stop_evt: asyncio.Event, base_rate: float, burst_rate: float) -> None:
    """Feed the bus at a jittered rate until stop_evt is set.

    Not used by the CLI smoke test directly but consumed by pipeline.py.
    """
    gen = Generator()
    tick_period = 0.1  # 10 ticks/sec
    while not stop_evt.is_set():
        now = time.time()
        # sinusoidal rate modulation + slight burst probability
        t = now % 60.0
        rate = base_rate + (burst_rate - base_rate) * max(0.0, math.sin(t / 60.0 * math.tau)) * 0.5
        n = max(1, int(rate * tick_period))
        for r in gen.tick(n, now):
            await bus.publish("logs", r)
        await asyncio.sleep(tick_period)
