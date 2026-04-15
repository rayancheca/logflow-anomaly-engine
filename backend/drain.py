"""A compact implementation of the Drain log parsing algorithm.

Drain (He et al., ICWS 2017) organizes log templates in a fixed-depth tree.
Each leaf holds a group of similar log messages; a new line either joins
the most similar group or creates a new template. This implementation keeps
the algorithm small (~120 lines) but follows the structure of the paper.

We use this to detect *structural* anomalies: an anomaly fires whenever a
brand-new template appears and exceeds a frequency threshold in-window.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterable

_PARAM_RX = re.compile(r"[0-9]+(?:\.[0-9]+)?|[a-f0-9]{8,}|sku_[a-zA-Z0-9]+|u_[0-9]+|id_[a-f0-9]+")


def _tokenize(message: str) -> list[str]:
    cleaned = _PARAM_RX.sub("<*>", message)
    return cleaned.split()


@dataclass
class LogGroup:
    template_id: int
    tokens: list[str]
    count: int = 0

    def similarity(self, tokens: list[str]) -> float:
        if len(tokens) != len(self.tokens):
            return 0.0
        same = sum(1 for a, b in zip(self.tokens, tokens) if a == b or a == "<*>")
        return same / max(len(tokens), 1)

    def merge(self, tokens: list[str]) -> None:
        self.tokens = [
            a if (a == b) else "<*>"
            for a, b in zip(self.tokens, tokens)
        ]
        self.count += 1

    def as_string(self) -> str:
        return " ".join(self.tokens)


@dataclass
class TreeNode:
    depth: int = 0
    children: dict[str, "TreeNode"] = field(default_factory=dict)
    groups: list[LogGroup] = field(default_factory=list)


class Drain:
    def __init__(self, depth: int = 4, similarity_threshold: float = 0.5, max_children: int = 100) -> None:
        # Depth counts token levels after (length, first_token).
        self.depth = depth
        self.st = similarity_threshold
        self.max_children = max_children
        self.root = TreeNode()
        self._next_id = 1
        self._new_templates: list[tuple[int, str]] = []

    def _get_leaf(self, tokens: list[str]) -> TreeNode:
        node = self.root
        length_key = f"len={len(tokens)}"
        node = node.children.setdefault(length_key, TreeNode(depth=1))
        for i in range(min(self.depth, len(tokens))):
            tok = tokens[i] if not tokens[i].startswith("<") else "<*>"
            if tok not in node.children:
                if len(node.children) >= self.max_children:
                    tok = "<*>"
                    node.children.setdefault(tok, TreeNode(depth=node.depth + 1))
                else:
                    node.children[tok] = TreeNode(depth=node.depth + 1)
            node = node.children[tok]
        return node

    def add(self, message: str) -> tuple[int, bool]:
        """Add a log message and return (template_id, is_new)."""
        tokens = _tokenize(message)
        if not tokens:
            return 0, False
        leaf = self._get_leaf(tokens)
        best: LogGroup | None = None
        best_sim = 0.0
        for g in leaf.groups:
            sim = g.similarity(tokens)
            if sim > best_sim:
                best_sim = sim
                best = g
        if best and best_sim >= self.st:
            best.merge(tokens)
            return best.template_id, False
        # New template
        tid = self._next_id
        self._next_id += 1
        new_group = LogGroup(template_id=tid, tokens=tokens[:], count=1)
        leaf.groups.append(new_group)
        self._new_templates.append((tid, new_group.as_string()))
        return tid, True

    def add_many(self, messages: Iterable[str]) -> list[tuple[int, bool]]:
        return [self.add(m) for m in messages]

    def drain_new_templates(self) -> list[tuple[int, str]]:
        """Return and clear the list of new templates since the last call."""
        out = self._new_templates[:]
        self._new_templates.clear()
        return out

    def total_templates(self) -> int:
        return self._next_id - 1

    def all_templates(self) -> list[tuple[int, str, int]]:
        out: list[tuple[int, str, int]] = []
        stack: list[TreeNode] = [self.root]
        while stack:
            node = stack.pop()
            stack.extend(node.children.values())
            for g in node.groups:
                out.append((g.template_id, g.as_string(), g.count))
        return sorted(out, key=lambda x: -x[2])
