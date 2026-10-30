#!/usr/bin/env python3
"""Move legacy analytics ledgers before starting a clean data epoch."""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LEGACY = {
    "rejected_shadow": ROOT / "data/analytics/shadow_counterfactual/rejected_shadow.jsonl",
    "entry_plans": ROOT / "data/analytics/entry_controller/entry_plans.jsonl",
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--archive-dir", default="data/analytics/archive/2026-09-01-contaminated")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    archive_dir = ROOT / args.archive_dir
    manifest = {
        "archived_at": datetime.now(timezone.utc).isoformat(),
        "reason": "pre-clean epoch archive; legacy records are excluded from new analytics",
        "files": [],
    }
    for name, source in LEGACY.items():
        if not source.exists():
            continue
        entry = {"name": name, "source": str(source.relative_to(ROOT)),
                 "records": sum(1 for line in source.open(encoding="utf-8") if line.strip()),
                 "sha256": sha256(source)}
        manifest["files"].append(entry)
        if not args.dry_run:
            archive_dir.mkdir(parents=True, exist_ok=True)
            shutil.move(str(source), str(archive_dir / source.name))
        print(f"{name}: {entry['records']} records | {entry['sha256']}")

    if not args.dry_run:
        archive_dir.mkdir(parents=True, exist_ok=True)
        (archive_dir / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"Archive created: {archive_dir.relative_to(ROOT)}")
    else:
        print("Dry run: no files copied")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
