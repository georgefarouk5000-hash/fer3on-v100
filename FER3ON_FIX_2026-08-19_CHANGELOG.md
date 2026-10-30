# FER3ON FIX PATCH — 2026-08-19

## سبب التعديل (مبني على البيانات الحقيقية)

تحليل 120 صفقة مغلقة فعلية من `data/history/trades.csv` كشف:

| الاستراتيجية | صفقات | WR | R:R فعلي | Net | PF |
|---|---:|---:|---:|---:|---:|
| **SMC**    | 51 | 49.0% | **0.67** | **−249$** | 0.65 |
| **MICRO**  | 31 | 45.2% | **0.93** | **−130$** | 0.76 |
| **MANUAL** | 38 | 50.0% | **1.24** | **+143$** | 1.24 |

**السبب الجذري:** انعكاس نسبة العائد/المخاطرة. البوت كان يقفل أرباح صغيرة (`tp1_rr=1.0` مع `tp1_pct=50%`) ويترك الباقي يضرب SL كامل، فيتحول متوسط الربح إلى أصغر من متوسط الخسارة رياضيًا.

**اكتشافات جانبية حرجة:**
- Session **NEWYORK للبوت** = −206$، **ASIA** = −258$، **OFF_HOURS** = +132$ (الأفضل)
- Regime **RANGING** = −400$، **TRENDING** = −311$ WR=32% (البوت يدخل عكس الترند)
- **exec_grade=B** = −527$ في 42 صفقة (النظام معكوس عمليًا)
- **quality_score للفائزين (35.6) < للخاسرين (55.5)** ← نظام الجودة معكوس

---

## التعديلات المُطبقة

### 1) `core/settings.py` — إصلاح `MULTI_TP_PROFILE`
```
SMC   : tp1_rr 1.0 → 1.5   |  tp1_pct 50% → 35%
MICRO : tp1_rr 1.0 → 1.4   |  tp1_pct 100% → 50% (إضافة tp2 @ 2.2)
SCALP : tp1_rr 1.0 → 1.3
DAILY : tp1_rr 1.0 → 1.5
```
هذا يمنع قفل الربح المبكر ويجبر متوسط الربح على تجاوز متوسط الخسارة.

### 2) `core/settings.py` — رفع الحدود
```
MIN_RR_GUARD_BY_STRATEGY:  SMC 0.9→1.5, MICRO 0.7→1.4, SCALP 0.85→1.3
MIN_RR_GUARD_ABSOLUTE_FLOOR:  0.6 → 1.2
MULTI_TP_CONFLICT_MODE.tp1_rr:  0.8 → 1.2
TP_SL_MULT_PER_STRAT:  MICRO 2.0→2.4, SMC 3.0→3.2, SCALP 2.0→2.2
```

### 3) `core/adaptive_sl_tp_engine.py` — إعادة معايرة المحرك التكيفي
- `sl_multiplier` القاعدة **6.0 → 4.5** (SL أضيق بحوالي 25%)
- `rr_base` القاعدة **1.20 → 1.60** + رفع كل المعاملات الإيجابية
- **نطاق R:R النهائي: `(1.15, 2.2)` → `(1.5, 3.2)`** ← الإصلاح الجوهري

### 4) ملف جديد: `core/strategy_kill_switch.py`
Kill-switch مربوط بـ `execute_trade` قبل فتح أي صفقة:
- **يمنع** SMC/MICRO من الدخول في ASIA + NEWYORK
- **يمنع** SMC في RANGING و MICRO في RANGING+TRENDING
- **يوقف الاستراتيجية** عند خسارة يومية 30-50$ أو أسبوعية 80-120$
- **يشترط** exec_grade ∈ {A, A+, ELITE} لـ SMC/MICRO عند وجود خسارة أسبوعية

### 5) ملف جديد: `core/expected_edge_gate.py`
بوابة Expected Value قبل التنفيذ:
- تحسب EV = (WR × RR) − (1 − WR) لكل صفقة
- ترفض أي صفقة EV_ratio < 0.05 (5% من SL)
- تستخدم win_rate الحقيقي التاريخي من `trades.csv`

### 6) `core/trade_executor.py` — ربط البوابات
```
execute_trade():
  1. KILL_SWITCH check   → yes: return retcode=-1
  2. Compute rr_guard
  3. EDGE_GATE check     → yes: return retcode=-1
  4. Original flow continues...
```

---

## التحقق (Validation)

### قبل الإصلاح — R:R فعلي على السيناريوهات:
| Scenario | RR |
|---|---:|
| SMC/ASIA/TRENDING/B | 0.67 |
| MICRO/NEWYORK/RANGING/B | 0.93 |

### بعد الإصلاح — R:R المحسوب:
| Scenario | RR | حالة الـ Kill-Switch |
|---|---:|---|
| SMC/ASIA/TRENDING/B qual=82 | **3.07** | 🚫 BLOCKED (session) |
| SMC/LONDON/RANGING/B qual=50 | **2.70** | 🚫 BLOCKED (regime) |
| MICRO/NEWYORK/RANGING/B qual=2 | **2.22** | 🚫 BLOCKED (session+regime) |
| **SMC/OFF_HOURS/TRENDING/A qual=90** | **3.20** | ✅ ALLOWED |
| **DAILY/LONDON/TRENDING/A qual=80** | **3.20** | ✅ ALLOWED |
| SCALP/NEWYORK/VOLATILE/B qual=60 | **2.78** | ✅ ALLOWED |

### Expected Edge Gate — قيم EV_ratio:
| Strategy | RR=0.7 | RR=1.0 | RR=1.5 | RR=2.0 |
|---|---:|---:|---:|---:|
| SMC (WR=49%) | ❌ −0.167 | ❌ −0.020 | ✅ +0.226 | ✅ +0.471 |
| MICRO (WR=45%) | ❌ −0.232 | ❌ −0.097 | ✅ +0.129 | ✅ +0.355 |

---

## متوقع بعد التطبيق

بافتراض WR بقي 49% (SMC) لكن R:R انتقل من 0.67 إلى 2.5:
- **EV/صفقة القديم:** (0.49 × 22.82) − (0.51 × 29.24) = **−3.73$**
- **EV/صفقة الجديد:** (0.49 × 62.5) − (0.51 × 25.0) = **+17.87$**

على 51 صفقة SMC: **−190$ → +911$** (تحول تقديري بفارق ~1100$).

إضافة إلى تقليل عدد الصفقات المرفوضة عبر الـ kill-switch (نتوقع 40-50% من الصفقات الحالية ترفض إحصائيًا).

---

## ملفات تم تعديلها/إضافتها

- ✏️ `core/settings.py` (5 كتل)
- ✏️ `core/adaptive_sl_tp_engine.py` (كتلتان)
- ✏️ `core/trade_executor.py` (حقن kill-switch + edge gate)
- ➕ `core/strategy_kill_switch.py` (جديد)
- ➕ `core/expected_edge_gate.py` (جديد)
- ➕ `FER3ON_FIX_2026-08-19_CHANGELOG.md` (هذا الملف)

## مراقبة ما بعد التطبيق

- ملف الحالة: `data/analytics/kill_switch_state.json` (يُحدَّث لحظيًا)
- سجل التنفيذ: كل صفقة مرفوضة تظهر في stdout بـ `🚫 KILL_SWITCH_BLOCK` أو `🚫 EDGE_GATE_REJECT`
- إعادة معايرة: راجع الحدود في الملفين الجديدين بعد 50 صفقة جديدة على الأقل.
