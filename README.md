# 🏛️ FER3ON-V100 — Institutional Personal Gold AI

> *Phase-1 Professional Stabilization · Portfolio Risk Authority · Truth Layer*

**FER3ON-V100** — نسخة مستقلة لتداول **XAUUSD**، مبنية على بنية FER3ON
مع التركيز على:

> **رفع كفاءة FER3ON · زيادة الفرص المنفذة · الحفاظ على الانضباط المؤسسي**

**الفلسفة الموحدة التي لم تتغير:**
* Single Decision Authority
* Portfolio Brain
* Unified Decision Layer

خارطة التطوير المستقبلية، بما فيها التوسع متعدد الرموز وموجّه الاستراتيجيات
وطريقة فرز المواد التعليمية، موثقة في
[docs/FUTURE_DEVELOPMENT_ROADMAP_AR.md](docs/FUTURE_DEVELOPMENT_ROADMAP_AR.md).

---

## 🎯 بنية FER3ON-V100

### 1. Portfolio Risk Authority — Authority جديد يدير المخاطر فقط

> في الإصدارات السابقة Authority كان يقوم بدورين (Direction + Risk).
> هذا تسبب في اختناق الفرص ورفض صفقات دون سبب للمخاطرة.
> يعتمد FER3ON-V100 على Portfolio Risk Authority لإدارة المخاطر.

| Authority التقليدي | Portfolio Risk Authority في FER3ON-V100 |
|---|---|
| يحدد الاتجاه | لا يحدد الاتجاه |
| يرفض لرفض cross-strategy conflict | يقبل التنوع بين الاستراتيجيات |
| وظيفتان في نفس الوقت | وظيفة واحدة: إدارة المخاطر |
| سبب اختناق | سبب سيولة قرارات |

**خريطة FER3ON-V100:**
```
Strategies
    ↓
Independent Evaluation
    ↓
Unified Decision
    ↓
Portfolio Risk Authority      ← (v3.5)
    ↓
Execution
```

### 2. Risk Unification

> `core/settings.py` هو المصدر الرسمي الوحيد للمخاطرة.
> أي قيمة في README / config / legacy تُتجاهل إذا تعارضت.

**أين يُقرأ MAX_DAILY_RISK؟**
فقط من `core/settings.py`. لا من `config/risk_config.py`. لا من README.

### 3. Candle Confirmation Upgrade

لا نعتمد REJECTION / INSIDE BAR / MOMENTUM BREAKOUT
على شمعة واحدة فقط. يجب شمعتان متتاليتان بنفس الاتجاه
أو شمعة تأكيد إضافية.

### 4. SMC Diagnostic Layer

`core/smc_debug_report.py` — يكشف أي جزء من SMC هو الذي يفشل:
- Liquidity Sweep Detection Rate
- BOS Detection Rate
- FVG Detection Rate
- OB Detection Rate
- Mitigation Detection Rate
- Breaker Detection Rate
- Retest Detection Rate

> لم يُعدّل منطق SMC الأساسي — فقط نعرف أين الفشل.

### 5. ML Runtime Downgrade

طالما ML != REAL:

| خاصية | FER3ON-V100 |
|---|---:|
| ML_AUTHORITY_WEIGHT | **0.00** (لا veto) |
| ML_ADVISOR_WEIGHT | 0.15 |
| BLOCK / REJECT / OVERRIDE | ❌ ممنوع |
| BOOST / PENALTY | ±5 points max |

### 6. Truth Layer

`analytics/truth_layer.py` — المصدر الوحيد للحقيقة:
- Trade History
- Win Rate, Profit Factor, Expectancy, Max DD
- Strategy Breakdown
- Session Breakdown
- Regime Breakdown

### 7. Open Position Limits

Position limits are configured for the active SMC and DAILY strategies.

---

## ⚡ الـ AI V1 في سطر واحد

> **"محركات كثيرة · أدوار أوضح · قرار واحد نهائي · تنفيذ متدرج."**

```
Evidence Engines  →  Composite Score  →  Unified Decision (4 outcomes)  →  Layered Execution
```

4 قرارات فقط:

| 🚫 HARD_BLOCK | 🟢 PASS_FULL | 🟡 PASS_REDUCED | 🔵 PASS_MICRO |
|---|---|---|---|
| catastrophic فقط | سوق ممتاز (×1.00 – ×1.20) | سوق جيد (×0.70) | سوق صعب لكن مع edge (×0.40) |

---

## 📂 ما الجديد في AI V1

### 🆕 ملف جديد: `core/ai_v1_authority.py`
السلطة النهائية الموحدة. يحوي:
- `AIV1Evidence` — جامع نتائج كل المحركات (legacy + new)
- `ai_v1_decide()` — نقطة الدخول الوحيدة لاتخاذ القرار
- `apply_ai_v1_risk()` — Unified Risk Shaping
- `print_brand_banner()` — هوية AI V1 عند التشغيل

### ♻️ إعادة توزيع السلطة في `main.py`
**Legacy `continue` rejections** التي كانت تقتل الصفقة سراً → الآن تتحول إلى **evidence penalties** تدخل في composite score:

| كان يرفع | في AI V1 |
|---|---|
| `❌ QUALITY TOO LOW for risk mapping → continue` | `add_legacy_rejection("QUALITY_RISK_MAP_FAIL")` + use reduced-size risk |
| `❌ ML REJECTED → continue` | `add_legacy_rejection("ML_REJECTED")` (-10) |
| `❌ FINAL BRAIN REJECTED → continue` | `add_legacy_rejection("FINAL_BRAIN_REJECT")` (-12) |
| `⏸ FINAL BRAIN PREFERS WAIT → continue` | `add_legacy_rejection("FINAL_BRAIN_WAIT")` (-8) |
| `⏸ V7 MICRO_TRIGGER: Waiting → continue` | `add_legacy_rejection("V7_MICRO_TIMING_WAIT")` (-3) |
| `❌ EXECUTION OPTIMIZER V2 BLOCKED → continue` | `add_legacy_rejection("OPTIMIZER_BLOCKED")` + tighter exec params |
| `🛡️ SURVIVAL_HOLD → continue` | `add_legacy_rejection("SURVIVAL_HOLD")` (-10) → unified يقرر حجمًا مخفضًا أو BLOCK |

### 📏 عتبات AI V1 (مخفّضة قليلاً + مرنة)

| البند | V6 | V7 | **AI V1** |
|---|---:|---:|---:|
| MIN_QUALITY_SCORE | 60 | 55 | **52** |
| QUALITY_ADAPTIVE_MIN_FLOOR | 48 | 42 | **40** |
| FINAL_BRAIN_REJECT_FLOOR | 48 | 44 | **42** |
| COMPOSITE_FULL_MIN | — | 72 | **70** |
| COMPOSITE_MICRO_MIN | — | 42 | **40** |
| ML_HARD_REJECT_THRESHOLD | 0.32 | 0.28 | **0.25** |

### 🛡️ Hard Caps (لا تُمس)

```python
HARD_RISK_MAX_PER_TRADE      = 0.50 %
HARD_RISK_DAILY_LOSS_PERCENT = 3.0  %
MAX_RISK_TOTAL               = 0.75 %
MAX_LOT                      = 0.30
```

---

## 🧬 كل محركات V6/V7 موجودة (لا حذف)

✅ SMC Entry Engine V2 · Confidence Engine V5.1 · Liquidity Intelligence + Map V2
✅ Market Structure V5.1 (CHOCH+BOS+HH/HL/LH/LL) · MTF Consensus
✅ Execution Quality (A+/A/B/C) · Execution Intelligence · Execution Optimizer V2
✅ Master Brain V3 · Final Brain (evidence) · Conflict Resolver
✅ ML Engine: GBM + Neural Network + RL · Meta-AI Orchestrator
✅ Self-Optimizer · Adaptive Weighting · Trade DNA · Context Memory
✅ Survival Intelligence (→ reduced-size execution path) · Anti-Revenge Recovery+
✅ Professional Candle Engine · Outcome Learning · Replay Memory
✅ News Filter · Crisis Intelligence · Account Protection · Daily Macro Engine

**جديد في V7 محفوظ في AI V1**: Unified Decision Engine · Adaptive Learning · Unified Bridge

---

## 🗂️ هيكل المجلدات

```
FER3ON-AI-V1/
├── README.md                        ← هذا الملف
├── AI_V1_ARCHITECTURE.md            ← التقرير الرسمي الكامل
├── main.py                          ← Unified Authority wiring
├── config.env · requirements.txt
│
├── core/
│   ├── ai_v1_authority.py           ★ جديد — السلطة الموحدة
│   ├── unified_decision.py          (من V7)
│   ├── unified_bridge.py            (من V7)
│   ├── adaptive_learning.py         (من V7)
│   ├── settings.py                  (محدّث AI V1)
│   ├── env_utils.py · mt5_compat.py (من V6)
│   └── … (كل المحركات الـ 70+)
│
├── brain/      analytics/    ml/      execution/    risk/
└── tests/    scripts/    tools/   docs/
```

## 🧩 Partial TP / TP Tier Support
- `core/settings.py` الآن يدعم `MULTI_TP_STRATEGY_ENABLED` لتفعيل أو تعطيل الـ partial TP بشكل مستقل لكل استراتيجية.
- `execution/multi_tp.py` يحترم هذا الضبط في `get_tp_ladder()` و `compute_tp_prices()`.
- `core/adaptive_sl_tp_engine.py` يعيد الآن `tp_tiers` في نتائج adaptive SL/TP، لتوفير أسعار وأحجام TP المتدرجة لأي استراتيجية.
- مسار SMC الحيّ يمرر سعر التنفيذ واتجاه الصفقة إلى المحرك؛ الوقف يرتكز على أقرب pivot مؤكد صالح مع buffer من ATR، والهدف يستخدم أقرب مستوى هيكلي يحقق RR بين 1.5 و3.2 ضمن سقف TP. عند غياب مستوى مناسب يستخدم الهدف إسقاط RR، بينما يمنع التنفيذ إذا تعارض حد الوسيط الأدنى مع سقف الوقف. درجات الإغلاق الجزئي تُحصر داخل سعر TP النهائي وتستعيد هذا الحد من الصفقة المفتوحة بعد إعادة التشغيل.
- يمكن اختيار طريقة SL/TP عبر `SLTP_MODE` في البيئة أو `core/settings.py`: `ADAPTIVE` (الافتراضي) أو `FIXED_ATR`. الوضع الثابت يستخدم معاملات ATR الحالية لكل استراتيجية، مع استمرار تطبيق سياسات الوقف النهائية وحدود الوسيط والمخاطر في كلا الوضعين. أعد تشغيل البرنامج بعد تغيير الوضع.
- عند ضبط بداية جديدة لسجل الصفقات، يحفظ `data/history/history_sync_baseline.json` وقت البداية؛ مزامنة MT5 تتجاهل الصفقات التي فُتحت قبله حتى لا تعيد السجلات القديمة إلى بيانات المشروع. هذا لا يمسح سجل الوسيط.

---

## 🚀 التشغيل

```bash
# Windows
install.bat            # تثبيت المكتبات
run_fast.bat           # تشغيل سريع للبوت
run_fast.bat test      # تشغيل سريع مع اختبارات سريعة
run_full.bat           # تشغيل شامل: تنظيف + فحوصات + البوت
python main.py         # تشغيل البوت يدويًا

# عند الإقلاع:
========================================================================
  🏛️  FER3ON AI V1  —  v1.0.0-AI-V1
  Institutional Personal Gold AI — Unified Decision, Layered Execution
========================================================================
  Doctrine: No deletion · Single authority · Layered execution
  Verdicts: HARD_BLOCK · PASS_FULL · PASS_REDUCED · PASS_MICRO
========================================================================
🚀 FER3ON AI V1 Starting...
✅ MT5 Connected
```

---

## 📡 Telegram Commands (نفس V6/V7)

```
/start · /stop · /stats · /report · /quality · /context · /optimize
/choch · /liqmap · /weights · /adapt · /retrain · /mlstats
/liquidity · /structure
```

---

## 🎯 شخصية AI V1

> **ذكي · مرن · احترافي · غير جبان · غير متهور.**

- في السوق **الممتاز** → FULL execution
- في السوق **الجيد** → REDUCED execution
- في السوق **الصعب لكن فيه edge** → reduced-size execution (حجم صغير، TP قريب)
- في **الكوارث الحقيقية** → HARD_BLOCK فقط

---

## 📊 العائد المتوقع (مقابل V6)

| المقياس | المتوقع |
|---|---|
| Trade Frequency | **× 2 – × 4** |
| WAIT غير الضروري | **↓ 70%+** |
| Veto داخلي متضارب | **حلّ تماماً** |
| Capital Protection | **=** (نفس hard caps) |
| دخول في السوق المتوسط/الصعب | **↑↑** |

---

## 🛡️ Safety Guarantees (لا تُمس)

1. ❌ **لا تداول** عند daily_loss_capped, emergency_stop, market_unsafe, news_pause, broker_unavailable
2. ❌ **لا تداول** عند AI meta orchestrator يطلب اتجاه عكسي بـ override_strength ≥ 0.85
3. ❌ **لا تداول** عند no_signal أو spread_catastrophic أو ATR_insufficient
4. 🛑 **demo/live** validation عند الإقلاع
5. 🛑 hard caps في `core/settings.py` غير قابلة للتجاوز برمجياً

---

## ✅ التحقق والتشغيل الآمن

قبل تشغيل Live Trading أو أي تغيير كبير، يُفضّل تنفيذ:

```bash
pytest -q tests/test_datetime_warnings.py tests/test_execution_orchestrator.py tests/test_production_intelligence.py tests/test_production_integrity.py
python scripts/smoke_test.py
```

وإذا كان الهدف هو التحقق من جاهزية التشغيل، فتأكد من:
- وجود ملف config.env مع القيم الضرورية
- أن نظام MT5 والبيانات متوفران
- أن watchdog لا يُظهر حالة degraded غير مبررة
- أن CI على GitHub يمر بنجاح

## 📚 وثائق إضافية

- [archive/legacy_docs](archive/legacy_docs) — المستندات التاريخية المؤرشفة
- [runtime](runtime) — ملفات التشغيل والحالة
- [docs/OPERATIONAL_RUNBOOK.md](docs/OPERATIONAL_RUNBOOK.md) — دليل التشغيل والآليات
- [docs/RISK_POLICY.md](docs/RISK_POLICY.md) — سياسة إدارة المخاطر
- [docs/FER3ON_V1_5_UPGRADE_NOTES.md](docs/FER3ON_V1_5_UPGRADE_NOTES.md) — ملاحظات الترقية
- [PROJECT_STRUCTURE.md](PROJECT_STRUCTURE.md) — وصف بنية المشروع
- [CHANGELOG.md](CHANGELOG.md) — سجل التغييرات
- [QUICKSTART.md](QUICKSTART.md) — دليل البدء السريع
- [tools/clean_repo.py](tools/clean_repo.py) — تنظيف تلقائي للملفات المؤقتة
- [tools/system_health_check.py](tools/system_health_check.py) — فحص صحة المشروع
- [tools/run_project_checks.py](tools/run_project_checks.py) — تشغيل اختبارات وفحوصات موحدة
- [tools/full_start.py](tools/full_start.py) — بدء موحد للتشغيل الكامل
- [tools/backup_restore.py](tools/backup_restore.py) — نسخ احتياطية واستعادة ملفات مهمة
- [tools/end_to_end_smoke.py](tools/end_to_end_smoke.py) — smoke test end-to-end بسيط
- [core/structured_logging.py](core/structured_logging.py) — logging موحد ومهيكل
- [`.github/workflows/python-ci.yml`](.github/workflows/python-ci.yml) — سير عمل CI موحد

---

**FER3ON AI V1** هو الصورة النهائية الموصوفة في `FER3ON_MASTER_CONTEXT`.
بُني بحفاظ كامل على فلسفة المشروع، بدون كسر للأركان، وبتركيز كامل على إزالة التعارضات الداخلية.

> 🏛️ *Institutional in protection · Adaptive in entry · Smart in down-sizing · Disciplined in commitment.*
