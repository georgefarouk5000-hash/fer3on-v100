from analytics.performance_repository import get_all_trades, get_all_trades_including_legacy
from core.settings import BUILD_ID


def test_active_performance_repository_excludes_legacy_and_unstamped_rows():
    active = get_all_trades()
    archive = get_all_trades_including_legacy()
    assert len(active) <= len(archive)
    assert all(trade.build_id == BUILD_ID for trade in active)


def test_legacy_archive_remains_available_for_audit():
    archive = get_all_trades_including_legacy()
    assert isinstance(archive, list)