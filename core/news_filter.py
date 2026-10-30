"""
FER3ON V3+++ — News Filter (UTC-Aware)
تفعيل فلتر الأخبار الذي كان معطلاً في V3.
"""

from datetime import datetime, timezone

HIGH_IMPACT_NEWS = [
    (12, 30, 'EUR_CPI'),
    (13, 30, 'USD_CPI'),
    (14, 30, 'USD_PPI'),
    (14, 15, 'USD_NFP'),
    (19, 0, 'FOMC'),
    (20, 30, 'FOMC_PR'),
    (13, 0, 'USD_UNEMP'),
    (15, 0, 'USD_GDP'),
]


def is_news_active(symbol: str = 'XAUUSD', window_minutes: int = 30) -> dict:
    """
    يعود بـ is_news=True إذا كنا في نافذة ±window_minutes من حدث عالي التأثير.
    """
    _ = symbol
    now = datetime.now(timezone.utc)
    closest = None
    closest_min = 9999.0
    for h, m, label in HIGH_IMPACT_NEWS:
        event_time = now.replace(hour=h, minute=m, second=0, microsecond=0)
        delta_min = abs((now - event_time).total_seconds() / 60.0)
        if delta_min < closest_min:
            closest_min = delta_min
            closest = label
    if closest_min <= window_minutes:
        impact = 'HIGH' if closest_min <= 5 else 'MEDIUM'
        return {
            'is_news': True,
            'impact': impact,
            'minutes_to_event': round(closest_min, 1),
            'event': closest,
        }
    if now.weekday() == 4 and 12 <= now.hour <= 15:
        return {
            'is_news': True,
            'impact': 'MEDIUM',
            'minutes_to_event': round(closest_min, 1),
            'event': 'FRIDAY_US_WINDOW',
        }
    return {
        'is_news': False,
        'impact': 'LOW',
        'minutes_to_event': 999,
        'event': None,
    }


def is_news_time():
    return is_news_active(window_minutes=15)['is_news']
