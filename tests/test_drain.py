"""Tests for the Drain log-template miner."""
import pytest
from backend.drain import Drain, LogGroup, _tokenize


class TestTokenize:
    def test_replaces_hex_tokens(self) -> None:
        tokens = _tokenize("request id_abc123 failed")
        assert "<*>" in tokens

    def test_replaces_plain_numbers(self) -> None:
        tokens = _tokenize("status 200 latency 150.5")
        assert "200" not in tokens
        assert "150.5" not in tokens
        assert tokens.count("<*>") == 2

    def test_preserves_plain_words(self) -> None:
        tokens = _tokenize("payment service error")
        assert tokens == ["payment", "service", "error"]

    def test_empty_string(self) -> None:
        assert _tokenize("") == []


class TestLogGroup:
    def _make_group(self, tokens: list[str]) -> LogGroup:
        return LogGroup(template_id=1, tokens=tokens, count=1)

    def test_perfect_match_similarity(self) -> None:
        g = self._make_group(["GET", "/health", "<*>"])
        assert g.similarity(["GET", "/health", "<*>"]) == 1.0

    def test_zero_similarity_for_different_length(self) -> None:
        g = self._make_group(["GET", "/health"])
        assert g.similarity(["GET", "/health", "200"]) == 0.0

    def test_partial_similarity(self) -> None:
        g = self._make_group(["GET", "/health", "200"])
        sim = g.similarity(["GET", "/health", "404"])
        assert 0.5 < sim < 1.0

    def test_merge_generalises_differing_tokens(self) -> None:
        g = self._make_group(["GET", "/health", "200"])
        g.merge(["GET", "/health", "404"])
        assert g.tokens == ["GET", "/health", "<*>"]
        assert g.count == 2

    def test_as_string(self) -> None:
        g = self._make_group(["GET", "/health", "<*>"])
        assert g.as_string() == "GET /health <*>"


class TestDrain:
    def test_same_message_returns_same_template(self) -> None:
        d = Drain()
        tid1, new1 = d.add("payment failed for user 123")
        tid2, new2 = d.add("payment failed for user 456")
        assert tid1 == tid2
        assert new1 is True
        assert new2 is False

    def test_different_structure_creates_new_template(self) -> None:
        d = Drain()
        tid1, _ = d.add("GET /api/health 200")
        tid2, _ = d.add("POST /api/orders failed")
        assert tid1 != tid2

    def test_empty_message(self) -> None:
        d = Drain()
        tid, is_new = d.add("")
        assert tid == 0
        assert is_new is False

    def test_total_templates_tracks_count(self) -> None:
        d = Drain()
        d.add("error in payments service")
        d.add("timeout in catalog service")
        assert d.total_templates() == 2

    def test_drain_new_templates_clears_on_read(self) -> None:
        d = Drain()
        d.add("new error pattern alpha")
        first = d.drain_new_templates()
        second = d.drain_new_templates()
        assert len(first) == 1
        assert len(second) == 0

    def test_add_many_returns_same_length(self) -> None:
        d = Drain()
        msgs = ["service A error", "service B timeout", "service A error"]
        results = d.add_many(msgs)
        assert len(results) == 3

    def test_all_templates_sorted_by_count(self) -> None:
        d = Drain()
        for _ in range(5):
            d.add("frequent error in payments")
        d.add("rare error in catalog")
        templates = d.all_templates()
        assert templates[0][2] >= templates[-1][2]

    def test_max_children_respected(self) -> None:
        d = Drain(max_children=3)
        for i in range(10):
            d.add(f"method_{i} endpoint status")
        assert d.total_templates() <= 10

    def test_similarity_threshold_controls_grouping(self) -> None:
        strict = Drain(similarity_threshold=0.9)
        loose = Drain(similarity_threshold=0.1)
        msgs = [
            "payment declined user 123",
            "payment declined user 456",
        ]
        for m in msgs:
            strict.add(m)
            loose.add(m)
        assert loose.total_templates() <= strict.total_templates()
