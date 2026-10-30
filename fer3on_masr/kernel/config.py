from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class PlatformConfig:
    root_path: Path
    symbol: str = "XAUUSD"
    supported_assets: tuple[str, ...] = (
        "XAUUSD", "EURUSD", "GBPUSD", "BTCUSD", "NAS100", "US30", "WTI", "XAGUSD"
    )
    timeframes: tuple[str, ...] = ("M1", "M5", "M15", "H1", "H4", "D1", "W1")
    history_window: int = 500
    max_risk_pct: float = 0.50
    max_total_risk_pct: float = 0.75
    max_lot: float = 0.30
    default_atr: float = 2.5
    plugin_paths: tuple[str, ...] = ()
    learning_center_path: Path | None = None
    knowledge_graph_path: Path | None = None
    telemetry_path: Path | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def build(cls, root_path: str | Path) -> "PlatformConfig":
        root = Path(root_path).resolve()
        return cls(
            root_path=root,
            learning_center_path=root / "learning_center",
            knowledge_graph_path=root / "data" / "masr_knowledge_graph.json",
            telemetry_path=root / "data" / "masr_telemetry.json",
        )

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        for key, value in list(data.items()):
            if hasattr(value, "as_posix"):
                data[key] = value.as_posix()
        return data
