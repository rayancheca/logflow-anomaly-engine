"""Lightweight EWMA forecaster for per-service error rate.

Not a full time-series model — just an exponentially weighted mean + a
running variance estimate. Good enough for a 10-second "what's about to
happen" readout in the service drawer.
"""
from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass, field


@dataclass
class Forecaster:
    alpha: float = 0.35
    _state: dict[str, float] = field(default_factory=dict)
    _variance: dict[str, float] = field(default_factory=dict)
    _samples: dict[str, deque[float]] = field(
        default_factory=lambda: defaultdict(lambda: deque(maxlen=40))
    )

    def update(self, service: str, value: float) -> None:
        prev = self._state.get(service)
        if prev is None:
            self._state[service] = value
            self._variance[service] = 0.0
        else:
            new_state = self.alpha * value + (1.0 - self.alpha) * prev
            diff = value - prev
            self._variance[service] = (
                self.alpha * (diff * diff) + (1.0 - self.alpha) * self._variance[service]
            )
            self._state[service] = new_state
        self._samples[service].append(value)

    def forecast(self, service: str) -> tuple[float, float]:
        mu = self._state.get(service, 0.0)
        sigma = self._variance.get(service, 0.0) ** 0.5
        return mu, sigma

    def services(self) -> list[str]:
        return list(self._state.keys())
