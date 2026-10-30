import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from tools.backup_restore import create_dated_backup, rotate_backups, _snapshot_dirs_sorted


def test_create_dated_backup_makes_timestamped_dir(tmp_path):
    source = tmp_path / "sample.txt"
    source.write_text("hello", encoding="utf-8")
    backup_root = tmp_path / "backups"

    snapshot_dir = create_dated_backup([source], backup_root, keep=10)

    assert snapshot_dir.exists()
    assert (snapshot_dir / "sample.txt").read_text(encoding="utf-8") == "hello"
    assert snapshot_dir.parent == backup_root


def test_rotate_keeps_only_the_n_most_recent(tmp_path):
    backup_root = tmp_path / "backups"
    backup_root.mkdir()

    # Fabricate 5 snapshot dirs with distinct timestamps (oldest to newest)
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    made = []
    for i in range(5):
        stamp = (base + timedelta(hours=i)).strftime("%Y%m%dT%H%M%SZ")
        d = backup_root / stamp
        d.mkdir()
        made.append(d)

    removed = rotate_backups(backup_root, keep=2)

    assert len(removed) == 3
    remaining = _snapshot_dirs_sorted(backup_root)
    assert len(remaining) == 2
    # the two newest should survive
    assert remaining == made[-2:]


def test_rotate_never_touches_non_snapshot_dirs(tmp_path):
    backup_root = tmp_path / "backups"
    backup_root.mkdir()
    (backup_root / "not_a_snapshot").mkdir()
    (backup_root / "README.md").write_text("keep me", encoding="utf-8")

    removed = rotate_backups(backup_root, keep=0)

    assert removed == []
    assert (backup_root / "not_a_snapshot").exists()
    assert (backup_root / "README.md").exists()


def test_rotate_by_max_age(tmp_path):
    backup_root = tmp_path / "backups"
    backup_root.mkdir()

    old_stamp = (datetime.now(timezone.utc) - timedelta(days=40)).strftime("%Y%m%dT%H%M%SZ")
    new_stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    (backup_root / old_stamp).mkdir()
    (backup_root / new_stamp).mkdir()

    removed = rotate_backups(backup_root, keep=100, max_age_days=30)

    assert len(removed) == 1
    assert removed[0].name == old_stamp
    assert (backup_root / new_stamp).exists()


def test_create_dated_backup_triggers_rotation(tmp_path):
    source = tmp_path / "sample.txt"
    source.write_text("hi", encoding="utf-8")
    backup_root = tmp_path / "backups"

    dirs = []
    for _ in range(3):
        dirs.append(create_dated_backup([source], backup_root, keep=2))
        time.sleep(1.01)  # ensure distinct second-resolution timestamps

    remaining = _snapshot_dirs_sorted(backup_root)
    assert len(remaining) == 2
    assert remaining == dirs[-2:]
