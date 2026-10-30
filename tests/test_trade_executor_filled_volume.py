from types import SimpleNamespace

import pytest

from core.trade_executor import get_filled_volume


@pytest.mark.parametrize(
    ("result", "fallback", "expected"),
    [
        (SimpleNamespace(volume=0.01), 0.02, 0.01),
        (SimpleNamespace(volume=0, request=SimpleNamespace(volume=0.01)), 0.02, 0.01),
        (SimpleNamespace(volume=None, request={"volume": 0.01}), 0.02, 0.01),
        (SimpleNamespace(volume=0, request=None), 0.02, 0.02),
    ],
)
def test_get_filled_volume_prefers_confirmed_fill_then_fallback(result, fallback, expected):
    assert get_filled_volume(result, fallback) == expected


def test_get_filled_volume_returns_zero_when_no_positive_volume_exists():
    result = SimpleNamespace(volume=0, request={"volume": -1})

    assert get_filled_volume(result, 0) == 0
