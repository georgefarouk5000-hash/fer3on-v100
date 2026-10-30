from __future__ import annotations

import ast
import json
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Set, Tuple

ROOT = Path(__file__).resolve().parents[1]
SKIP_DIRS = {".git", ".pytest_cache", "__pycache__", "archive", "docs", "data", "runtime"}


def py_files() -> List[Path]:
    files: List[Path] = []
    for path in ROOT.rglob("*.py"):
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        files.append(path)
    return sorted(files)


def module_name(path: Path) -> str:
    rel = path.relative_to(ROOT).with_suffix("")
    return ".".join(rel.parts)


def resolve_relative(base_mod: str, imported: str | None, level: int) -> str:
    if level == 0:
        # Absolute import ("from core.settings import X") — resolves to the
        # imported module directly, with no anchor to the importing module's
        # own path.
        return imported if imported else base_mod
    parts = base_mod.split(".")
    anchor = parts[:-level]
    if imported:
        return ".".join(anchor + imported.split("."))
    return ".".join(anchor)


def parse_imports(path: Path) -> Tuple[Set[str], List[str], List[str]]:
    imports: Set[str] = set()
    imported_names: List[str] = []
    assigned_names: List[str] = []
    try:
        tree = ast.parse(path.read_text(encoding="utf-8", errors="ignore"))
    except Exception:
        return imports, imported_names, assigned_names

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.add(alias.name)
                imported_names.append(alias.asname or alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            base = resolve_relative(module_name(path), node.module, node.level)
            imports.add(base)
            for alias in node.names:
                imported_names.append(alias.asname or alias.name)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            assigned_names.append(node.name)
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    assigned_names.append(target.id)
    return imports, imported_names, assigned_names


def find_used_names(path: Path) -> Set[str]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8", errors="ignore"))
    except Exception:
        return set()
    used: Set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
            used.add(node.id)
    return used


def build_graph():
    mods = {module_name(p): p for p in py_files()}
    internal_prefixes = tuple(sorted({m.split(".")[0] for m in mods}))
    deps: Dict[str, Set[str]] = defaultdict(set)
    imported_names_map: Dict[str, List[str]] = {}
    used_names_map: Dict[str, Set[str]] = {}

    for mod, path in mods.items():
        imports, imported_names, _assigned = parse_imports(path)
        imported_names_map[mod] = imported_names
        used_names_map[mod] = find_used_names(path)
        for imp in imports:
            if imp in mods:
                deps[mod].add(imp)
            else:
                # fallback: map package imports to concrete modules when possible
                for candidate in mods:
                    if candidate == imp or candidate.startswith(imp + "."):
                        deps[mod].add(candidate)
                        break
                else:
                    if imp.startswith(internal_prefixes):
                        deps[mod].add(imp)
    return mods, deps, imported_names_map, used_names_map


def categorize_dead_candidates(mods: Dict[str, Path], incoming: Dict[str, Set[str]]) -> Dict[str, List[str]]:
    runtime_roots = {
        "main",
        "core.settings",
        "core.startup_check",
        "core.fer3on_decision_authority",
        "core.trade_executor",
    }
    tests_or_tools = {m for m in mods if m.startswith(("tests.", "testing.", "tools.", "scripts."))}
    candidates = []
    for mod in mods:
        if mod in runtime_roots:
            continue
        if mod in tests_or_tools:
            continue
        if not incoming.get(mod):
            candidates.append(mod)
    return {
        "zero_inbound_non_runtime": sorted(candidates),
        "tests_and_tools_only": sorted(m for m in mods if m in tests_or_tools),
    }


def detect_legacy(mods: Dict[str, Path]) -> Dict[str, List[str]]:
    legacy = {"V5": [], "V6": [], "V7": [], "ai_v1_authority": []}
    for mod, path in mods.items():
        text = path.read_text(encoding="utf-8", errors="ignore")
        if "V5" in text:
            legacy["V5"].append(mod)
        if "V6" in text:
            legacy["V6"].append(mod)
        if "V7" in text:
            legacy["V7"].append(mod)
        if "ai_v1_authority" in text or mod == "core.ai_v1_authority":
            legacy["ai_v1_authority"].append(mod)
    return {k: sorted(v) for k, v in legacy.items()}


def possible_unused_imports(mods: Dict[str, Path], imported_names_map: Dict[str, List[str]], used_names_map: Dict[str, Set[str]]) -> Dict[str, List[str]]:
    result: Dict[str, List[str]] = {}
    for mod in mods:
        imported = imported_names_map.get(mod, [])
        used = used_names_map.get(mod, set())
        suspects = []
        for name in imported:
            head = name.split(".")[0]
            if head == "*":
                continue
            if head not in used:
                suspects.append(name)
        if suspects:
            result[mod] = sorted(set(suspects))
    return result


def find_duplicate_roles(mods: Dict[str, Path]) -> Dict[str, List[str]]:
    groups = {
        "decision_layers": [],
        "risk_layers": [],
        "execution_layers": [],
        "memory_layers": [],
        "runtime_validation_layers": [],
    }
    for mod in mods:
        low = mod.lower()
        if "decision" in low or "authority" in low or low.endswith("unified_bridge"):
            groups["decision_layers"].append(mod)
        if "risk" in low:
            groups["risk_layers"].append(mod)
        if "execution" in low or "trade_executor" in low:
            groups["execution_layers"].append(mod)
        if "memory" in low:
            groups["memory_layers"].append(mod)
        if any(token in low for token in ["startup_check", "system_health_check", "end_to_end_smoke", "v7_audit", "runtime_validation", "module_registry", "spec_runtime"]):
            groups["runtime_validation_layers"].append(mod)
    return {k: sorted(v) for k, v in groups.items()}


def main() -> None:
    mods, deps, imported_names_map, used_names_map = build_graph()
    incoming: Dict[str, Set[str]] = defaultdict(set)
    for src, targets in deps.items():
        for dst in targets:
            incoming[dst].add(src)

    report = {
        "module_count": len(mods),
        "incoming_edges": {k: sorted(v) for k, v in incoming.items()},
        "dead_candidates": categorize_dead_candidates(mods, incoming),
        "legacy_markers": detect_legacy(mods),
        "possible_unused_imports": possible_unused_imports(mods, imported_names_map, used_names_map),
        "duplicate_roles": find_duplicate_roles(mods),
    }
    out = ROOT / "data" / "analytics" / "architecture_runtime_audit.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(out)


if __name__ == "__main__":
    main()
