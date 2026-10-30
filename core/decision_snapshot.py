import json
import os
from copy import deepcopy
from datetime import datetime, timezone

OPEN_SNAPSHOTS_FILE = "data/analytics/open_trade_snapshots.json"
CLOSED_SNAPSHOTS_DIR = "data/analytics/decision_snapshots"


def initialize_snapshot_store():
    os.makedirs(os.path.dirname(OPEN_SNAPSHOTS_FILE), exist_ok=True)
    os.makedirs(CLOSED_SNAPSHOTS_DIR, exist_ok=True)
    if not os.path.exists(OPEN_SNAPSHOTS_FILE):
        with open(OPEN_SNAPSHOTS_FILE, "w", encoding="utf-8") as f:
            json.dump({}, f, indent=2, ensure_ascii=False)


def _load_open_snapshots():
    initialize_snapshot_store()
    try:
        with open(OPEN_SNAPSHOTS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _save_open_snapshots(data):
    initialize_snapshot_store()
    with open(OPEN_SNAPSHOTS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def register_open_trade(snapshot, identifiers):
    data = _load_open_snapshots()
    payload = deepcopy(snapshot)
    payload.setdefault("snapshot_created_at", datetime.now(timezone.utc).isoformat())
    payload.setdefault("status", "OPEN")

    aliases = []
    for ident in identifiers or []:
        if ident in (None, "", 0, "0"):
            continue
        aliases.append(str(ident))
    aliases = list(dict.fromkeys(aliases))
    payload["snapshot_aliases"] = aliases

    for alias in aliases:
        data[alias] = payload

    _save_open_snapshots(data)
    return payload


def get_open_trade_snapshot(*identifiers):
    data = _load_open_snapshots()
    for ident in identifiers:
        if ident in (None, "", 0, "0"):
            continue
        found = data.get(str(ident))
        if found:
            return deepcopy(found)
    return None


def complete_trade_snapshot(close_info, *identifiers):
    data = _load_open_snapshots()
    snapshot = None
    matched_aliases = []

    for ident in identifiers:
        if ident in (None, "", 0, "0"):
            continue
        alias = str(ident)
        if alias in data:
            snapshot = deepcopy(data[alias])
            matched_aliases = snapshot.get("snapshot_aliases", [alias])
            break

    if snapshot is None:
        snapshot = {}

    snapshot.update(close_info or {})
    snapshot["status"] = "CLOSED"
    snapshot["closed_at"] = datetime.now(timezone.utc).isoformat()

    ticket = str(snapshot.get("ticket") or snapshot.get("close_ticket") or (identifiers[0] if identifiers else datetime.now(timezone.utc).timestamp()))
    out_path = os.path.join(CLOSED_SNAPSHOTS_DIR, f"{ticket}.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(snapshot, f, indent=2, ensure_ascii=False)

    for alias in matched_aliases:
        data.pop(str(alias), None)
    _save_open_snapshots(data)
    return snapshot
