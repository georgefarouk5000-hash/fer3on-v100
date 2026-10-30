import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PYTHON = sys.executable


def main() -> int:
    print("\n▶ FER3ON-AI-V2 FULL START")
    print("Preparing runtime and validating project state...\n")

    cleanup = subprocess.run([PYTHON, "tools/clean_repo.py"], cwd=str(ROOT), check=False)
    if cleanup.returncode != 0:
        return cleanup.returncode

    checks = subprocess.run([PYTHON, "tools/run_project_checks.py"], cwd=str(ROOT), check=False)
    if checks.returncode != 0:
        return checks.returncode

    print("\n▶ Starting main runtime...")
    return subprocess.run([PYTHON, "main.py"], cwd=str(ROOT), check=False).returncode


if __name__ == "__main__":
    raise SystemExit(main())
