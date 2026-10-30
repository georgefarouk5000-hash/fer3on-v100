from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class ApiDescriptor:
    rest_routes: tuple[str, ...]
    websocket_topics: tuple[str, ...]
    external_channels: tuple[str, ...]


def default_api_descriptor() -> ApiDescriptor:
    return ApiDescriptor(
        rest_routes=("/health", "/decision", "/reports/market", "/reports/timeframes"),
        websocket_topics=("market.snapshot", "decision.execution", "learning.update"),
        external_channels=("telegram", "discord", "mobile_app", "web_dashboard"),
    )
