import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def _run_cli(*args):
    return subprocess.run(
        [sys.executable, "-m", "fer3on", *args],
        cwd=str(REPO_ROOT), capture_output=True, text=True, encoding="utf-8",
        errors="replace", timeout=60,
    )


def test_no_args_prints_help_and_fails():
    result = _run_cli()
    assert result.returncode == 1
    assert "Usage:" in result.stdout


def test_help_flag_prints_help_and_succeeds():
    result = _run_cli("--help")
    assert result.returncode == 0
    assert "Commands:" in result.stdout


def test_unknown_command_fails_with_message():
    result = _run_cli("not-a-real-command")
    assert result.returncode == 1
    assert "Unknown command" in result.stdout


def test_ci_gate_delegates_and_passes_through_args():
    result = _run_cli("ci-gate", "--bars", "300")
    assert result.returncode == 0
    assert "CI SHADOW BACKTEST GATE" in result.stdout
    assert "Bars:        300" in result.stdout


def test_backtest_delegates_and_passes_through_args():
    result = _run_cli("backtest", "--bars", "300", "--mode", "stats")
    assert result.returncode == 0


def test_readiness_delegates():
    result = _run_cli("readiness")
    assert "DEVELOPMENT READINESS GATE" in result.stdout
    # verdict may be READY or NOT_READY depending on repo state -- just
    # confirm it ran and printed a verdict line, don't assert exit code.
    assert "VERDICT" in result.stdout


def test_cleanup_memory_delegates(tmp_path):
    import os

    # Run with an isolated cwd containing an empty ai_memory.csv so this
    # test can never touch the real project data. PYTHONPATH keeps the
    # fer3on package importable (python -m needs it on sys.path) while
    # cwd controls where the script's relative "data/memory/..." path
    # actually resolves.
    data_dir = tmp_path / "data" / "memory"
    data_dir.mkdir(parents=True)
    (data_dir / "ai_memory.csv").touch()

    env = {**os.environ, "PYTHONPATH": str(REPO_ROOT)}
    result = subprocess.run(
        [sys.executable, "-m", "fer3on", "cleanup-memory"],
        cwd=str(tmp_path), capture_output=True, text=True, encoding="utf-8",
        errors="replace", timeout=30, env=env,
    )
    assert "تنظيف ai_memory.csv" in result.stdout
    assert "فارغ أصلًا" in result.stdout
