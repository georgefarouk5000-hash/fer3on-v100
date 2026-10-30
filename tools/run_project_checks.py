import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    commands = [
        [sys.executable, "-m", "pytest", "-q", "tests/test_datetime_warnings.py", "tests/test_execution_orchestrator.py", "tests/test_production_intelligence.py", "tests/test_production_integrity.py"],
        [sys.executable, "tools/system_health_check.py"],
    ]

    for command in commands:
        print(f"\n▶ Running: {' '.join(command)}")
        completed = subprocess.run(command, cwd=str(ROOT), check=False)
        if completed.returncode != 0:
            return completed.returncode

    print("\nAll project checks completed successfully.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
