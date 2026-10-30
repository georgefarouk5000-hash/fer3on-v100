from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


class LearningCenter:
    def __init__(self, root_path: str | Path) -> None:
        self.root = Path(root_path)
        self.root.mkdir(parents=True, exist_ok=True)
        self.index_path = self.root / "index.json"
        if not self.index_path.exists():
            self.index_path.write_text("[]", encoding="utf-8")

    def _load_index(self) -> list[dict[str, Any]]:
        return json.loads(self.index_path.read_text(encoding="utf-8"))

    def _save_index(self, rows: list[dict[str, Any]]) -> None:
        self.index_path.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")

    def register_artifact(self, path: str | Path, category: str, tags: list[str] | None = None) -> dict[str, Any]:
        file_path = Path(path)
        file_path.parent.mkdir(parents=True, exist_ok=True)
        if not file_path.exists():
            file_path.write_text("", encoding="utf-8")
        rows = self._load_index()
        digest = hashlib.sha1(file_path.as_posix().encode("utf-8")).hexdigest()[:12]
        row = {
            "id": digest,
            "path": file_path.as_posix(),
            "category": category,
            "tags": tags or [],
            "size": file_path.stat().st_size,
        }
        rows = [r for r in rows if r.get("path") != row["path"]]
        rows.append(row)
        self._save_index(rows)
        return row

    def search(self, keyword: str) -> list[dict[str, Any]]:
        keyword = keyword.lower().strip()
        return [
            row
            for row in self._load_index()
            if keyword in row.get("path", "").lower() or any(keyword in tag.lower() for tag in row.get("tags", []))
        ]
