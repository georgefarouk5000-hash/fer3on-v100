"""
FER3ON — unified CLI

Usage:
    python -m fer3on <command> [args...]

Commands:
    masr            Run the live MASR trading loop        (was: run_masr.py)
    backtest        Strategy backtest harness              (was: run_backtest.py)
    faie-backtest   FAIE historical backtest harness        (was: run_faie_backtest.py)
    faie-shadow     Run FAIE in shadow mode                 (was: run_faie_shadow.py)
    audit           FAIE self-audit                         (was: run_faie_self_audit.py)
    train           Train the ML model                      (was: run_ml_train.py)
    ci-gate         CI shadow-backtest gate                 (was: tools/ci_shadow_backtest_gate.py)
    readiness       Development readiness checklist          (was: tools/development_readiness_gate.py)
    cleanup-memory  Clean stale OPEN/SYNC rows from ai_memory.csv (was: scripts/cleanup_ai_memory.py)

Examples:
    python -m fer3on masr
    python -m fer3on backtest --csv data/backtest_data/last_90d.csv --mode full
    python -m fer3on train --analyze
    python -m fer3on ci-gate --csv data/backtest_data/last_90d.csv
    python -m fer3on readiness
    python -m fer3on cleanup-memory --full

This is an additive convenience layer, not a replacement: every command
above is a thin delegator to the existing standalone script of the same
purpose, which is left working unchanged (any existing automation calling
`python run_backtest.py` etc. directly keeps working). This just gives a
single, harder-to-typo entry point on top of the six separate scripts (plus
four .bat/.ps1 launchers) that previously had to be run individually.
Remaining CLI args after the command name are passed straight through to
the target script's own argument parser -- `python -m fer3on backtest
--csv X` behaves identically to `python run_backtest.py --csv X`.
"""

from __future__ import annotations

import importlib
import sys

COMMANDS = {
    "masr": ("fer3on_masr.app", "main"),
    "backtest": ("run_backtest", "main"),
    "faie-backtest": ("run_faie_backtest", "main"),
    "faie-shadow": ("run_faie_shadow", "main"),
    "audit": ("run_faie_self_audit", "main"),
    "train": ("run_ml_train", "main"),
    "ci-gate": ("tools.ci_shadow_backtest_gate", "main"),
    "readiness": ("tools.development_readiness_gate", "main"),
    "cleanup-memory": ("scripts.cleanup_ai_memory", "main"),
}


def _print_help() -> None:
    print(__doc__)


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)

    if not argv:
        _print_help()
        return 1

    if argv[0] in ("-h", "--help"):
        _print_help()
        return 0

    command, rest = argv[0], argv[1:]
    if command not in COMMANDS:
        print(f"Unknown command: {command!r}\n")
        _print_help()
        return 1

    module_name, func_name = COMMANDS[command]
    module = importlib.import_module(module_name)
    func = getattr(module, func_name)

    # Delegate remaining args exactly as if the target script had been
    # invoked directly -- its own argparse (or absence of one) reads
    # sys.argv unchanged.
    sys.argv = [f"{module_name.replace('.', '/')}.py", *rest]
    result = func()
    return result if isinstance(result, int) else 0


if __name__ == "__main__":
    raise SystemExit(main())
