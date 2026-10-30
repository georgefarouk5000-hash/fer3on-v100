from __future__ import annotations

from typing import Any


class ServiceRegistry:
    def __init__(self) -> None:
        self._services: dict[str, Any] = {}

    def register(self, name: str, service: Any) -> Any:
        self._services[name] = service
        return service

    def get(self, name: str, default: Any = None) -> Any:
        return self._services.get(name, default)

    def snapshot(self) -> dict[str, str]:
        return {name: type(service).__name__ for name, service in self._services.items()}
