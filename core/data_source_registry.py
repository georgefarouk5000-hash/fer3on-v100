"""Canonical data-source registry, intended for use by analytics and validation.

This module defines the single approved collection of data sources, meant to
avoid mixing legacy files, backups, and runtime artifacts into the same
source graph.

AUDIT NOTE: as of this build, no live analytics or validation code actually
imports this registry -- it's only consumed by its own governance test
(tests/test_governance_p0.py), which checks internal consistency (unique
names, valid canonical keys/paths) but doesn't verify that anything reads
from it. Same orphaned-module shape as core/risk_policy.py; noted here so it
isn't mistaken for something actively enforced today.
"""

from __future__ import annotations

from typing import Any, Dict

DATA_SOURCE_REGISTRY: Dict[str, Dict[str, Any]] = {
    "truth_layer": {
        "name": "truth_layer",
        "canonical_key": "truth_layer",
        "path": "data/truth_layer/trade_history.json",
        "category": "canonical",
        "read_only": True,
    },
    "analytics_snapshot": {
        "name": "analytics_snapshot",
        "canonical_key": "analytics_snapshot",
        "path": "data/analytics/certification_status.json",
        "category": "derived",
        "read_only": True,
    },
    "daily_report": {
        "name": "daily_report",
        "canonical_key": "daily_report",
        "path": "data/analytics/daily_performance_report.md",
        "category": "derived",
        "read_only": True,
    },
    "runtime_state": {
        "name": "runtime_state",
        "canonical_key": "runtime_state",
        "path": "runtime/",
        "category": "runtime",
        "read_only": False,
    },
}


def resolve_data_source(key: str) -> Dict[str, Any] | None:
    """Return a data source definition by canonical key or alias."""
    normalized = (key or "").strip().lower()
    if not normalized:
        return None

    if normalized in DATA_SOURCE_REGISTRY:
        return DATA_SOURCE_REGISTRY[normalized]

    for source in DATA_SOURCE_REGISTRY.values():
        if source["name"] == normalized or source["canonical_key"] == normalized:
            return source

    return None


def get_canonical_sources() -> Dict[str, Dict[str, Any]]:
    return dict(DATA_SOURCE_REGISTRY)
