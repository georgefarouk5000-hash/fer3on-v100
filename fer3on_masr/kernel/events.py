from __future__ import annotations

from collections import defaultdict
from typing import Any, Callable


class EventBus:
    def __init__(self) -> None:
        self._listeners: dict[str, list[Callable[[dict[str, Any]], None]]] = defaultdict(list)

    def subscribe(self, event_name: str, callback: Callable[[dict[str, Any]], None]) -> None:
        self._listeners[event_name].append(callback)

    def publish(self, event_name: str, payload: dict[str, Any]) -> None:
        for callback in list(self._listeners.get(event_name, [])):
            callback(payload)

    def listener_count(self, event_name: str) -> int:
        return len(self._listeners.get(event_name, []))
