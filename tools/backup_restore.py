import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, List, Optional


def backup_paths(paths: Iterable[Path], backup_dir: Path) -> List[Path]:
    backup_dir.mkdir(parents=True, exist_ok=True)
    copied: List[Path] = []
    for path in paths:
        source = Path(path)
        if not source.exists():
            continue
        target = backup_dir / source.name
        if source.is_dir():
            shutil.copytree(source, target, dirs_exist_ok=True)
        else:
            shutil.copy2(source, target)
        copied.append(target)
    return copied


def restore_paths(paths: Iterable[Path], backup_dir: Path, restore_dir: Path) -> List[Path]:
    restore_dir.mkdir(parents=True, exist_ok=True)
    restored: List[Path] = []
    for path in paths:
        source = Path(path)
        backup_path = backup_dir / source.name
        if not backup_path.exists():
            continue
        target = restore_dir / source.name
        if backup_path.is_dir():
            shutil.copytree(backup_path, target, dirs_exist_ok=True)
        else:
            shutil.copy2(backup_path, target)
        restored.append(target)
    return restored


# =============================================================================
# Rotation policy (cleanup recommendation: "حذف data/backups المتراكمة
# برنامجياً (rotation policy) — قد تنفخ الحجم بلا فائدة")
# =============================================================================
# backup_paths()/restore_paths() above are unmodified primitives (existing
# tests still pass unchanged). The functions below add dated, prunable
# snapshots on top: each call to create_dated_backup() gets its own
# timestamped subdirectory instead of everyone overwriting the same
# target, and rotate_backups() prunes old ones so data/backups can't grow
# without bound.

_SNAPSHOT_DIR_FORMAT = "%Y%m%dT%H%M%SZ"


def create_dated_backup(
    paths: Iterable[Path],
    backup_root: Path,
    keep: int = 10,
    max_age_days: Optional[int] = None,
) -> Path:
    """Back up `paths` into a new timestamped subdirectory of `backup_root`,
    then immediately prune old snapshots per rotate_backups(). Returns the
    new snapshot directory.
    """
    backup_root = Path(backup_root)
    snapshot_name = datetime.now(timezone.utc).strftime(_SNAPSHOT_DIR_FORMAT)
    snapshot_dir = backup_root / snapshot_name
    # Extremely unlikely collision (same second) — fall back to a suffix
    # rather than silently overwriting a prior snapshot.
    suffix = 1
    while snapshot_dir.exists():
        snapshot_dir = backup_root / f"{snapshot_name}-{suffix}"
        suffix += 1

    backup_paths(paths, snapshot_dir)
    rotate_backups(backup_root, keep=keep, max_age_days=max_age_days)
    return snapshot_dir


def _snapshot_dirs_sorted(backup_root: Path) -> List[Path]:
    """Dated snapshot subdirectories under backup_root, oldest first.
    Anything not matching the timestamp format is left alone entirely —
    rotation must never guess at and delete a directory it didn't create.
    """
    if not backup_root.exists():
        return []
    dirs = []
    for entry in backup_root.iterdir():
        if not entry.is_dir():
            continue
        name = entry.name.split("-")[0]  # strip collision suffix, if any
        try:
            stamp = datetime.strptime(name, _SNAPSHOT_DIR_FORMAT).replace(tzinfo=timezone.utc)
        except ValueError:
            continue  # not one of ours — never touch it
        dirs.append((stamp, entry))
    dirs.sort(key=lambda pair: pair[0])
    return [entry for _stamp, entry in dirs]


def rotate_backups(
    backup_root: Path,
    keep: int = 10,
    max_age_days: Optional[int] = None,
) -> List[Path]:
    """Delete old dated snapshots under backup_root: keep at most `keep`
    most-recent ones, and (if max_age_days is given) also delete any
    snapshot older than that regardless of count. Returns the list of
    directories removed. Only ever touches directories this module itself
    created (see _snapshot_dirs_sorted) -- never a generic "delete
    everything old in this folder" sweep.
    """
    backup_root = Path(backup_root)
    snapshots = _snapshot_dirs_sorted(backup_root)  # oldest first

    to_delete: List[Path] = []

    if keep is not None and keep >= 0 and len(snapshots) > keep:
        to_delete.extend(snapshots[: len(snapshots) - keep])

    if max_age_days is not None:
        cutoff = datetime.now(timezone.utc).timestamp() - (max_age_days * 86400)
        for snap in snapshots:
            if snap in to_delete:
                continue
            name = snap.name.split("-")[0]
            try:
                stamp = datetime.strptime(name, _SNAPSHOT_DIR_FORMAT).replace(tzinfo=timezone.utc)
            except ValueError:
                continue
            if stamp.timestamp() < cutoff:
                to_delete.append(snap)

    removed: List[Path] = []
    for snap in to_delete:
        try:
            shutil.rmtree(snap)
            removed.append(snap)
        except Exception as error:
            print(f"⚠️ BACKUP_ROTATION_DELETE_FAILED (non-fatal) for {snap}: {error}")

    return removed
