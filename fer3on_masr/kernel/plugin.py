from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


class Plugin(Protocol):
    name: str

    def setup(self, context: object) -> None: ...


@dataclass(slots=True)
class PluginManager:
    plugins: list[Plugin]

    def setup_all(self, context: object) -> list[str]:
        loaded: list[str] = []
        for plugin in self.plugins:
            plugin.setup(context)
            loaded.append(plugin.name)
        return loaded
