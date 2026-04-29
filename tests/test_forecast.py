"""Tests for the EWMA Forecaster."""
import pytest
from backend.forecast import Forecaster


class TestForecaster:
    def test_first_update_sets_state(self) -> None:
        f = Forecaster()
        f.update("payments", 0.05)
        mu, sigma = f.forecast("payments")
        assert mu == pytest.approx(0.05)
        assert sigma == pytest.approx(0.0)

    def test_second_update_moves_toward_new_value(self) -> None:
        f = Forecaster(alpha=0.5)
        f.update("payments", 0.0)
        f.update("payments", 1.0)
        mu, _ = f.forecast("payments")
        assert 0.0 < mu < 1.0

    def test_stable_signal_converges_near_constant(self) -> None:
        f = Forecaster(alpha=0.35)
        for _ in range(100):
            f.update("payments", 0.1)
        mu, _ = f.forecast("payments")
        assert mu == pytest.approx(0.1, abs=1e-4)

    def test_variance_zero_for_constant_signal(self) -> None:
        f = Forecaster(alpha=0.35)
        for _ in range(50):
            f.update("payments", 0.05)
        _, sigma = f.forecast("payments")
        assert sigma == pytest.approx(0.0, abs=0.01)

    def test_variance_positive_for_noisy_signal(self) -> None:
        f = Forecaster(alpha=0.5)
        values = [0.0, 1.0, 0.0, 1.0, 0.0, 1.0]
        for v in values:
            f.update("payments", v)
        _, sigma = f.forecast("payments")
        assert sigma > 0.0

    def test_unknown_service_returns_zero(self) -> None:
        f = Forecaster()
        mu, sigma = f.forecast("unknown")
        assert mu == 0.0
        assert sigma == 0.0

    def test_services_lists_tracked_names(self) -> None:
        f = Forecaster()
        f.update("payments", 0.1)
        f.update("catalog", 0.2)
        assert set(f.services()) == {"payments", "catalog"}

    def test_independent_services_dont_interfere(self) -> None:
        f = Forecaster(alpha=1.0)  # last-value wins
        f.update("a", 0.1)
        f.update("b", 0.9)
        mu_a, _ = f.forecast("a")
        mu_b, _ = f.forecast("b")
        assert mu_a == pytest.approx(0.1)
        assert mu_b == pytest.approx(0.9)

    def test_alpha_controls_responsiveness(self) -> None:
        slow = Forecaster(alpha=0.05)
        fast = Forecaster(alpha=0.95)
        for _ in range(10):
            slow.update("s", 0.0)
            fast.update("s", 0.0)
        slow.update("s", 1.0)
        fast.update("s", 1.0)
        mu_slow, _ = slow.forecast("s")
        mu_fast, _ = fast.forecast("s")
        assert mu_fast > mu_slow
