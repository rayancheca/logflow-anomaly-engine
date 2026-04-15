"""Kafka-shaped async pub/sub.

This gives us the same mental model as confluent-kafka — producers publish
to a named topic, one or more independent consumer groups receive every
message — but runs entirely in-process with zero infrastructure. Swapping
to real Kafka later means replacing this one file.
"""
from __future__ import annotations

import asyncio
from typing import AsyncIterator, Generic, TypeVar

T = TypeVar("T")


class Subscriber(Generic[T]):
    def __init__(self, name: str, maxsize: int) -> None:
        self.name = name
        self.queue: asyncio.Queue[T] = asyncio.Queue(maxsize=maxsize)
        self.dropped = 0

    async def deliver(self, msg: T) -> None:
        try:
            self.queue.put_nowait(msg)
        except asyncio.QueueFull:
            # Drop oldest to keep freshness — same policy as a bounded Kafka consumer
            try:
                _ = self.queue.get_nowait()
                self.dropped += 1
            except asyncio.QueueEmpty:
                pass
            try:
                self.queue.put_nowait(msg)
            except asyncio.QueueFull:
                self.dropped += 1

    async def stream(self) -> AsyncIterator[T]:
        while True:
            msg = await self.queue.get()
            yield msg


class StreamBus:
    """In-memory topic bus with multiple consumer groups per topic."""

    def __init__(self, maxsize: int = 10_000) -> None:
        self._topics: dict[str, list[Subscriber]] = {}
        self._maxsize = maxsize
        self.published = 0

    def subscribe(self, topic: str, group: str) -> Subscriber:
        sub = Subscriber(group, self._maxsize)
        self._topics.setdefault(topic, []).append(sub)
        return sub

    async def publish(self, topic: str, msg) -> None:
        self.published += 1
        for sub in self._topics.get(topic, []):
            await sub.deliver(msg)

    def stats(self) -> dict[str, int]:
        return {
            "published": self.published,
            "topics": len(self._topics),
            "subscribers": sum(len(v) for v in self._topics.values()),
        }
