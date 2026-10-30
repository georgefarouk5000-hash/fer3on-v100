# FER3ON SMART COUNTER-TRADING ENGINE
# [FER3ON-FIX-2026-09-02]

## Overview
**Smart Counter-Trading** استراتيجية تحويل الانحيازات القوية من مشكلة إلى فرصة. بدل محاربة الانحياز (4:1 نحو SELL) أو تجاهله، نستغله بفتح صفقات عكسية صغيرة.

## Problem (الدافع)
```
تحليل البيانات: 
- 2523 إشارة تاريخية
- 79.43% SELL | 20.57% BUY
- النسبة: 3.86:1 نحو SELL

السؤال: لماذا نحارب هذا الانحياز؟
الحل: نستغله! إذا كانت إشارات SELL مهيمنة، نأخذ BUY عكسي بحجم أصغر.
```

## Algorithm

### 1. Bias Detection
```python
ratio = SELL_count / BUY_count
strong_bias = ratio > 3.0 or ratio < 0.33  # 3:1 في أي اتجاه
```

### 2. Confidence Calculation
```
إذا ratio = 4.0 (SELL 80%)
confidence = 0.3 + (4.0 - 1.0) / 10.0 = 0.6 (60%)

كلما زاد الانحياز → زادت الثقة
لكن: أقصى ثقة = 0.8 (80%) — لا نتجرأ أكثر
```

### 3. Position Sizing
```
original_lot = 0.10
counter_lot = 0.10 × 0.5 = 0.05  # نصف الحجم (أأمن)

original_sl = $30
counter_sl = $30 × 0.6 = $18  # أضيق (نقطة توقف أقرب)

original_tp = $50
counter_tp = $50 × 0.8 = $40  # أرباح أصغر (أسرع خروج)
```

## Usage

### Automatic Advisory Mode (الوضع الحالي)
```python
# main.py يطبع هذا تلقائياً بعد فتح صفقة:
[SMART-COUNTER-ADVISORY] | Signal: BUY | Lot: 0.05 | Confidence: 0.6 | 
Strong bias detected: SELL dominant (ratio > 3.0) → taking opportunistic BUY with reduced size/stops
```

### Manual Execution (المستقبل)
إذا أردت تنفيذ موقع عكسي يدوياً:
```python
from core.smart_counter_trading import get_counter_position

counter = get_counter_position(
    original_signal='SELL',
    original_lot=0.10,
    original_sl=30.0,
    original_tp=50.0,
)

if counter:
    print(f"خذ {counter['counter_signal']} بـ {counter['counter_lot']} لوت")
    # نفّذ الموقع هنا
```

### Monitoring & Statistics
```python
from core.smart_counter_trading import get_counter_trading_summary

stats = get_counter_trading_summary()
# {
#   'total_counter_trades': 45,
#   'wins': 27,
#   'success_rate': 60.0,
#   'avg_confidence': 0.65
# }
```

## Configuration

جميع الثوابت موجودة في `core/smart_counter_trading.py`:
- `BIAS_THRESHOLD = 3.0` — أدنى انحياز لتفعيل العكس
- `MAX_CONFIDENCE = 0.8` — أعلى ثقة (لا نتجرأ أكثر)
- `LOT_MULTIPLIER = 0.5` — الحجم العكسي = 50% من الأصلي
- `SL_MULTIPLIER = 0.6` — SL العكسي = 60% من الأصلي
- `TP_MULTIPLIER = 0.8` — TP العكسي = 80% من الأصلي

## Safety Guards

```
1. لا نفتح موقع عكسي إذا كان الانحياز ضعيفاً (< 3:1)
2. أقصى ثقة = 80% حتى في أقوى الانحيازات
3. الحجم العكسي = نصف الحجم الأصلي (تقليل الخطر)
4. SL أضيق (60% فقط) = خسارة أصغر
5. TP أصغر (80%) = أرباح أسرع

النتيجة: حتى لو الموقع خسر، الخسارة محدودة جداً
```

## Logging

السجل يُحفظ في: `data/counter_trades_log.jsonl`

مثال:
```json
{
  "timestamp": "2026-09-02T12:34:56.789Z",
  "original_signal": "SELL",
  "counter_signal": "BUY",
  "counter_lot": 0.05,
  "counter_sl": 18.0,
  "counter_tp": 40.0,
  "confidence": 0.6,
  "reasoning": "Strong bias detected: SELL dominant (ratio > 3.0) → taking opportunistic BUY with reduced size/stops"
}
```

## Performance Targets

استهداف إحصائي:
- **Success Rate**: 55-65% (أعلى من العشوائي، أقل من الإشارات الأساسية)
- **Avg Win Size**: صغيرة (~$5-10 على $100 حساب)
- **Avg Loss Size**: أصغر من Avg Win (نسبة RR > 1:1)
- **Total Trades**: قليلة نسبياً (تفعّل فقط عند انحياز قوي جداً)

**الهدف الأساسي**: ليس الربح الضخم، بل استغلال فرص "أرجحية" أثناء فترات الانحياز.

## Integration Points

| ملف | الدور |
|-----|-------|
| `core/smart_counter_trading.py` | المحرك الأساسي |
| `main.py` | التفعيل (Advisory شامل) |
| `analytics/` | تحليل النتائج (مستقبلاً) |

## Future Enhancements

```
[ ] مراقبة تلقائية لـ Win Rate
[ ] تعديل dynamic للـ multipliers بناءً على أداء حقيقي
[ ] تكامل مع Phase 3 Institutional Shadow
[ ] تقارير يومية للإحصائيات
[ ] A/B testing: Counter ON vs OFF
```

## Disable/Enable

لتعطيل Smart Counter-Trading مؤقتاً:
```python
# في main.py:
_SMART_COUNTER_AVAILABLE = False  # أو مع حذف الاستيراد
```

---

**تاريخ التطبيق**: 2026-09-02  
**الحالة**: Advisory Mode (لا تنفيذ تلقائي)  
**الأداء**: قيد المراقبة
