import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional


class StructuredLogger:
    def __init__(self, log_path: Optional[str] = None, console: bool = True):
        self.log_path = Path(log_path) if log_path else None
        self.console = console
        self._logger = logging.getLogger("fer3on_ai_v2")
        self._logger.setLevel(logging.INFO)
        self._logger.propagate = False
        if not self._logger.handlers:
            formatter = logging.Formatter("%(message)s")
            handler = logging.StreamHandler()
            handler.setFormatter(formatter)
            self._logger.addHandler(handler)

    def _emit(self, level: str, message: str, extra: Optional[Dict[str, Any]] = None) -> None:
        payload = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": level,
            "message": message,
            **(extra or {}),
        }
        line = json.dumps(payload, ensure_ascii=False)
        if self.log_path:
            self.log_path.parent.mkdir(parents=True, exist_ok=True)
            with self.log_path.open("a", encoding="utf-8") as handle:
                handle.write(line + "\n")
        if self.console:
            self._logger.info(line)

    def info(self, message: str, extra: Optional[Dict[str, Any]] = None) -> None:
        self._emit("INFO", message, extra)

    def warning(self, message: str, extra: Optional[Dict[str, Any]] = None) -> None:
        self._emit("WARNING", message, extra)

    def error(self, message: str, extra: Optional[Dict[str, Any]] = None) -> None:
        self._emit("ERROR", message, extra)
