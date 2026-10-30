import csv
import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
GATE_SCRIPT = REPO_ROOT / "tools" / "ci_shadow_backtest_gate.py"


def _write_fake_csv(path: Path, n=400, seed=1):
    import numpy as np
    rng = np.random.default_rng(seed)
    price = 2000.0
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["open", "high", "low", "close"])
        for _ in range(n):
            change = rng.normal(0, 2.5)
            o = price
            c = price + change
            h = max(o, c) + abs(rng.normal(0, 1))
            l = min(o, c) - abs(rng.normal(0, 1))
            w.writerow([o, h, l, c])
            price = c


def _run_gate(*extra_args):
    result = subprocess.run(
        [sys.executable, str(GATE_SCRIPT), *extra_args],
        cwd=str(REPO_ROOT), capture_output=True, text=True, encoding="utf-8",
        errors="replace", timeout=60,
    )
    return result


def test_smoke_mode_never_fails_on_expectancy(tmp_path):
    result = _run_gate("--bars", "300")
    assert result.returncode == 0
    assert "SYNTHETIC" in result.stdout
    assert "NOT an expectancy gate" in result.stdout


def test_bootstraps_baseline_on_first_real_run(tmp_path):
    csv_path = tmp_path / "fake.csv"
    baseline_path = tmp_path / "baseline.json"
    _write_fake_csv(csv_path)

    result = _run_gate("--csv", str(csv_path), "--baseline-path", str(baseline_path))
    assert result.returncode == 0
    assert baseline_path.exists()
    data = json.loads(baseline_path.read_text())
    assert "expectancy" in data


def test_passes_when_within_tolerance(tmp_path):
    csv_path = tmp_path / "fake.csv"
    baseline_path = tmp_path / "baseline.json"
    _write_fake_csv(csv_path)

    _run_gate("--csv", str(csv_path), "--baseline-path", str(baseline_path))
    result = _run_gate("--csv", str(csv_path), "--baseline-path", str(baseline_path))
    assert result.returncode == 0
    assert "Within tolerance" in result.stdout


def test_fails_when_regression_exceeds_threshold(tmp_path):
    csv_path = tmp_path / "fake.csv"
    baseline_path = tmp_path / "baseline.json"
    _write_fake_csv(csv_path)

    _run_gate("--csv", str(csv_path), "--baseline-path", str(baseline_path))
    data = json.loads(baseline_path.read_text())
    data["expectancy"] = abs(data["expectancy"]) * 3 + 100  # force a huge inflated baseline
    baseline_path.write_text(json.dumps(data))

    result = _run_gate("--csv", str(csv_path), "--baseline-path", str(baseline_path), "--max-regression-pct", "5")
    assert result.returncode == 1
    assert "BLOCKING MERGE" in result.stdout


def test_update_baseline_flag_overwrites(tmp_path):
    csv_path = tmp_path / "fake.csv"
    baseline_path = tmp_path / "baseline.json"
    _write_fake_csv(csv_path)

    _run_gate("--csv", str(csv_path), "--baseline-path", str(baseline_path))
    original = json.loads(baseline_path.read_text())["expectancy"]

    result = _run_gate("--csv", str(csv_path), "--baseline-path", str(baseline_path), "--update-baseline")
    assert result.returncode == 0
    updated = json.loads(baseline_path.read_text())["expectancy"]
    assert updated == original  # same data -> same expectancy, just re-saved
