import csv
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "cleanup_ai_memory.py"

sys.path.insert(0, str(REPO_ROOT))
from core.data_integrity import AI_MEMORY_COLUMNS as COLUMNS  # noqa: E402
# [FER3ON-FIX-2026-08-28] كانت نسخة منفصلة مكررة يدويًا هنا (بالظبط الخطأ
# اللي الاختبار ده بيحمي منه للسكريبت نفسه) — كل ما الscheme الحقيقي
# يتغيّر (زي إضافة account_id) كانت بتقدّم من غير قصد. استوردناها من
# المصدر الحقيقي عشان تتزامن تلقائيًا للأبد.


def _row(ticket, result, exec_grade):
    row = {c: "" for c in COLUMNS}
    row.update(ticket=ticket, result=result, exec_grade=exec_grade)
    return row


def _write_ai_memory(path: Path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=COLUMNS)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def _run(cwd, *args):
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        cwd=str(cwd), capture_output=True, text=True, encoding="utf-8",
        errors="replace", timeout=30,
    )


def _read_ai_memory(path: Path):
    if not path.exists():
        return []
    with open(path, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def test_empty_file_reports_nothing_to_clean(tmp_path):
    ai_memory_path = tmp_path / "data" / "memory" / "ai_memory.csv"
    ai_memory_path.parent.mkdir(parents=True)
    ai_memory_path.touch()  # exists but zero bytes -> read_all_rows returns []

    result = _run(tmp_path)
    assert "فارغ أصلًا" in result.stdout


def test_default_mode_keeps_real_closed_removes_open_and_sync(tmp_path):
    ai_memory_path = tmp_path / "data" / "memory" / "ai_memory.csv"
    rows = [
        _row("1", "OPEN", "A"),        # stuck open -> removed
        _row("2", "OPEN", "B"),        # stuck open -> removed
        _row("3", "WIN", "SYNC"),      # orphaned sync placeholder -> removed
        _row("4", "LOSS", "SYNC"),     # orphaned sync placeholder -> removed
        _row("5", "WIN", "A+"),        # real closed trade -> kept
        _row("6", "LOSS", "B"),        # real closed trade -> kept
    ]
    _write_ai_memory(ai_memory_path, rows)

    result = _run(tmp_path)
    assert result.returncode == 0

    # backup created
    backups = list((tmp_path / "data" / "memory").glob("ai_memory_backup_*.csv"))
    assert len(backups) == 1
    assert len(_read_ai_memory(backups[0])) == 6  # backup has all original rows

    remaining = _read_ai_memory(ai_memory_path)
    assert len(remaining) == 2
    assert {r["ticket"] for r in remaining} == {"5", "6"}


def test_full_mode_wipes_everything(tmp_path):
    ai_memory_path = tmp_path / "data" / "memory" / "ai_memory.csv"
    rows = [
        _row("1", "OPEN", "A"),
        _row("2", "WIN", "A+"),
    ]
    _write_ai_memory(ai_memory_path, rows)

    result = _run(tmp_path, "--full")
    assert result.returncode == 0

    backups = list((tmp_path / "data" / "memory").glob("ai_memory_backup_*.csv"))
    assert len(backups) == 1
    assert len(_read_ai_memory(backups[0])) == 2  # backup preserved pre-wipe data

    remaining = _read_ai_memory(ai_memory_path)
    assert remaining == []


def test_output_schema_matches_real_ai_memory_columns(tmp_path):
    """Guards against the exact bug this script had during development:
    a hand-duplicated column list drifted from the real schema (missing
    master_breakdown/decision_snapshot_id). The script must import the
    real AI_MEMORY_COLUMNS, not maintain its own copy.
    """
    ai_memory_path = tmp_path / "data" / "memory" / "ai_memory.csv"
    _write_ai_memory(ai_memory_path, [_row("1", "WIN", "A")])

    _run(tmp_path)

    with open(ai_memory_path, encoding="utf-8") as fh:
        header = fh.readline().strip().split(",")
    assert "master_breakdown" in header
    assert "decision_snapshot_id" in header
    assert len(header) == len(COLUMNS)
