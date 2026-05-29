"""Lightweight in-process event bus."""

from __future__ import annotations

from collections import defaultdict
from typing import Callable, TypeVar

from adaptive_soundscape.core.events import EventPayload

T = TypeVar("T", bound=EventPayload)
Listener = Callable[[EventPayload], None]


class EventBus:
    """Simple typed pub/sub for subsystem coordination."""

    def __init__(self) -> None:
        self._listeners: dict[type, list[Listener]] = defaultdict(list)

    def subscribe(self, event_type: type[T], listener: Listener) -> None:
        self._listeners[event_type].append(listener)

    def unsubscribe(self, event_type: type[T], listener: Listener) -> None:
        listeners = self._listeners.get(event_type, [])
        if listener in listeners:
            listeners.remove(listener)

    def publish(self, event: EventPayload) -> None:
        for event_type, listeners in self._listeners.items():
            if isinstance(event, event_type):
                for listener in list(listeners):
                    listener(event)
