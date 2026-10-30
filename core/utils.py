# =========================================
# SHARED UTILITIES
# =========================================

def calculate_ema(prices, period):
    """
    EMA صحيح: يبدأ بـ SMA للـ N شمعة الأولى
    بدل prices[0] الخاطئة
    """
    if not prices or len(prices) < 2:
        return prices[0] if prices else 0

    # إذا البيانات أقل من الـ period ابدأ بـ SMA لكل ما هو موجود
    seed_count = min(period, len(prices))
    ema = sum(prices[:seed_count]) / seed_count

    multiplier = 2 / (period + 1)
    for price in prices[seed_count:]:
        ema = (price - ema) * multiplier + ema

    return ema
