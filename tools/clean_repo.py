import os
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

TARGET_DIRS = [
    "__pycache__",
    ".pytest_cache",
    "runtime/logs",
    "runtime/state",
]

TARGET_EXTENSIONS = [".log", ".sqlite", ".sqlite3", ".db", ".tmp", ".bak"]


def clean_repo() -> int:
    removed = []
    for rel in TARGET_DIRS:
        path = ROOT / rel
        if path.exists():
            shutil.rmtree(path, ignore_errors=True)
            removed.append(str(path.relative_to(ROOT)))

    for path in ROOT.rglob("*"):
        if not path.is_file():
            continue
        if path.suffix.lower() in TARGET_EXTENSIONS:
            try:
                path.unlink()
                removed.append(str(path.relative_to(ROOT)))
            except Exception:
                pass

    print("Cleaned repository artifacts:")
    for item in removed:
        print(f" - {item}")
    return 0


if __name__ == "__main__":
    raise SystemExit(clean_repo())
