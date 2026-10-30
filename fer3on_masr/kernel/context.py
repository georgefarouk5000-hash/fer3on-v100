from __future__ import annotations

from dataclasses import dataclass

from .config import PlatformConfig
from .events import EventBus
from .registry import ServiceRegistry


@dataclass(slots=True)
class PlatformContext:
    config: PlatformConfig
    event_bus: EventBus
    registry: ServiceRegistry


def build_context(root_path: str) -> PlatformContext:
    config = PlatformConfig.build(root_path)
    event_bus = EventBus()
    registry = ServiceRegistry()
    registry.register("config", config)
    registry.register("event_bus", event_bus)
    return PlatformContext(config=config, event_bus=event_bus, registry=registry)
