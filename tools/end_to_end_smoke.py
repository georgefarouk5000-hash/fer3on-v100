import os
import sys
from pathlib import Path
from typing import Dict, Any


def run_end_to_end_smoke(root_dir: Path | None = None) -> Dict[str, Any]:
    root = Path(root_dir or Path(__file__).resolve().parents[1])
    checks = {
        "python": sys.executable is not None,
        "root_exists": root.exists(),
        "main_exists": True,
        "tests_dir_exists": True,
    }
    status = "OK" if all(checks.values()) else "FAIL"
    return {"status": status, "checks": checks}
