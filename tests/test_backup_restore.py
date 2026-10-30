from pathlib import Path

from tools.backup_restore import backup_paths, restore_paths


def test_backup_and_restore_roundtrip(tmp_path):
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    target_file = source_dir / "sample.txt"
    target_file.write_text("hello", encoding="utf-8")

    backup_dir = tmp_path / "backup"
    backup_paths([target_file], backup_dir)

    assert (backup_dir / target_file.name).exists()

    restored_dir = tmp_path / "restored"
    restore_paths([target_file], backup_dir, restored_dir)

    assert (restored_dir / target_file.name).read_text(encoding="utf-8") == "hello"
