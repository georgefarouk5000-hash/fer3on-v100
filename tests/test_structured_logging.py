import json
from pathlib import Path

from core.structured_logging import StructuredLogger


def test_structured_logger_writes_json_lines(tmp_path):
    log_path = tmp_path / "test.log"
    logger = StructuredLogger(log_path=str(log_path), console=False)

    logger.info("hello", extra={"symbol": "XAUUSD"})

    assert log_path.exists()
    payload = json.loads(log_path.read_text(encoding="utf-8").strip().splitlines()[-1])
    assert payload["level"] == "INFO"
    assert payload["message"] == "hello"
    assert payload["symbol"] == "XAUUSD"
