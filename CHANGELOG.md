# FER3ON-V100 — CHANGELOG

> This is the single canonical changelog for the project root (per the
> repo cleanup: root previously had two changelogs plus 20+ scattered
> status reports). For the full historical changelog with per-item IDs
> (`[SLTP-1]`, `[EXPOSURE-1]`, etc. — still cited throughout inline code
> comments), see `docs/history/FER3ON_FINAL_CHANGELOG.md`. Obsolete
> point-in-time status and implementation reports have been removed.

## [Unreleased] — Trade Audit and Protected Stops

* Label confirmed swing pivots (HH/HL/LH/LL) and record the selected
  protected swing, stop buffer, and selection/fallback reason.
* Correlate a decision, each MT5 send attempt, the execution result, and
  partial/final closes with one persisted decision ID.
* Record entry reasons and confirmed conditions (including BOS, CHOCH, FVG,
  order blocks, sweeps, and retests) with each opened trade; use existing
  shadow and Truth Layer analytics to compare actual and rejected setups.
* Inventory shadow-mode systems in one machine-readable and Markdown report.
  Require a review after 100 resolved outcomes and a human promote-to-demo or
  remove/redesign decision after 200; report generation never changes live
  settings.
* Use one stable closed-bar candidate ID across shadow evaluators and actual
  trade attribution; exclude legacy heartbeat IDs and repeated rows from sample
  counts.
* Resolve hypothetical pullback-entry and alternate-exit outcomes from candle
  history with conservative same-bar stop/target handling, and compare them
  with cost-complete closed-trade P&L when correlation is available.
* Aggregate position P&L across opening and closing deals, including
  commission, swap, and fees; apply final win/loss outcomes once per position.
* Preserve the existing $100 daily-loss guard, MT5 validation, and SL/risk caps.

## [3.5.0] — PHASE-1 PROFESSIONAL STABILIZATION

### الهدف
رفع كفاءة FER3ON وزيادة عدد الفرص المنفذة مع الحفاظ على الانضباط
المؤسسي وتقليل الاختناق الحالي داخل طبقة اتخاذ القرار
— دون المساس بمنطق الاستراتيجيات الأساسية.

### القاعدة الذهبية
ممنوع حذف أو إلغاء:
* Single Decision Authority
* Portfolio Brain
* Unified Decision Layer

### التغيير الرئيسي: تحويل Authority
**`core/portfolio_risk_authority.py`** — Authority الجديد يدير المخاطر فقط:

| مسموح لـ Authority | ممنوع على Authority |
|---|---|
| Risk Control | رفض صفقة بسبب اختلاف استراتيجية أخرى |
| Lot Allocation | قرار الاتجاه BUY/SELL |
| Exposure Management | الحكم "مين على حق" |
| Portfolio Limits | |
| Daily Loss Protection | |
| Drawdown Protection | |

### Risk Unification
`core/settings.py` هو المصدر الرسمي الوحيد للمخاطرة.
أي قيمة في README / config / legacy files تتجاهل إذا تعارضت.

### MICRO Soft Stabilization (+10% تشدد)
| البند | القديم | V3.5 |
|---|---:|---:|
| Confidence | 30 → 35 | صارم |
| Confidence | 35 → 40 | صارم |
| Score      | 55 → 60 | صارم |
| Score      | 60 → 65 | صارم |
| شمعتان متتاليتان | لا | مؤكد | (Candle Confirmation)

### Candle Confirmation Upgrade
* REJECTION / INSIDE BAR / MOMENTUM BREAKOUT
  لا تُقبل الآن إلا بعد شمعتين متتاليتين بنفس الاتجاه
  أو شمعة تأكيد إضافية.
* يحقق منع الدخول على كل نبضة صغيرة.

### SMC Engine Improvement (بدون تعديل المنطق الأساسي)
* **`core/smc_debug_report.py`** — Diagnostic Layer جديد
* تقارير لكل يوم:
  * Liquidity Sweep Detection Rate
  * BOS Detection Rate
  * FVG Detection Rate
  * OB Detection Rate
  * Mitigation Detection Rate
  * Breaker Detection Rate
  * Retest Detection Rate

### ML Runtime Downgrade
طالما ML_STATUS != REAL:

```python
ML_AUTHORITY_WEIGHT = 0     # لا veto
ML_ADVISOR_WEIGHT   = 0.15  # advisor فقط
ML_BOOST_MAX_POINTS = +5
ML_PENALTY_MAX_PTS  = -5
ML_BLOCK_ALLOWED    = False
ML_REJECT_ALLOWED   = False
ML_OVERRIDE_ALLOWED = False
```

### Truth Layer
* **`analytics/truth_layer.py`** — المصدر الوحيد للحقيقة.
* Trade History · Win Rate · Profit Factor · Expectancy · Max DD
* Strategy Breakdown · Session Breakdown · Regime Breakdown

### Setup Analyzer
* **`analytics/setup_analyzer.py`** — يجيب على:
  "أي Setup يربح فعلاً؟"

### Execution Verification
* **`tests/test_live_execution.py`** — يختبر:
  Order Send · SL Validation · TP Validation · Invalid Stops
  Requotes · Volume Validation · Market Closed · Trade Context Busy

### Open Position Limits
`MAX_OPEN_TRADES = 4` — بحد أقصى:
* SCALP = 1
* MICRO = 1
* SMC = 1
* SWING أو DAILY = 1

### Architecture
```
Strategies
    ↓
Independent Evaluation
    ↓
Unified Decision
    ↓
Portfolio Risk Authority   ← v3.5
    ↓
Execution
```

### Phase-1 Acceptance Tests
كل التعديلات لا تعتمد قبل نجاح:

1. **Risk Consistency Test**            — `tests/test_risk_consistency.py`
2. **Authority Isolation Test**         — `tests/test_authority_isolation.py`
3. **Truth Layer Test**                 — `tests/test_truth_layer.py`
4. **Micro Stability Test**             — `tests/test_micro_stability.py`
5. **SMC Diagnostic Test**              — `tests/test_smc_diagnostic.py`
6. **Execution Verification Test**      — `tests/test_live_execution.py`
7. **Performance Validation Test**      — `tests/test_performance_validation.py`

Run all via:

```
python tools/phase1_acceptance.py
```

### ما لم يتغير
- Single Decision Authority
- Portfolio Brain
- Unified Decision Layer
- Logic الأساسي للاستراتيجيات
- MT5 integration layer

### ما هو خارج النطاق (Phase-2/3)
- بناء XGB الحقيقي
- بناء RL الحقيقي
- Walk Forward Testing
- Live Learning Validation
