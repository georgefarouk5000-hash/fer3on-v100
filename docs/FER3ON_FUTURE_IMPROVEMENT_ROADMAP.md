# FER3ON Future Improvement Roadmap

**الحالة:** مرجع تنفيذ مستقبلي - غير مفعّل
**التاريخ:** 2026-08-21
**النطاق:** جميع الاقتراحات المعمارية والتشغيلية المقترحة قبل هذه الوثيقة
**قاعدة أساسية:** لا يغيّر هذا الملف سلوك البوت ولا يمنح موافقة على التداول الحقيقي.

## 1. الهدف العام

تطوير FER3ON إلى نظام منظم يختار أفضل فرصة متاحة، ويعرف متى ينتظر، ومتى يدخل، ومتى يحمي الربح، ومتى لا يتداول، مع إمكانية تفسير كل قرار وقياسه بعد التنفيذ.

المبدأ المركزي:

```text
Data Quality
-> Signal Snapshot
-> Decision Authority
-> Risk Plan
-> Entry Plan
-> Exit Plan
-> Execution
-> Position Management
-> Truth Attribution
-> Learning
```

لا تتم إضافة طبقات ذكية جديدة قبل تثبيت هذا المسار.

## 2. المرحلة صفر: التثبيت والتنظيف المعماري

### 2.0 أولوية أمنية قبل أي توسعة

قبل تنفيذ أي طبقة Entry/Exit أو Opportunity Allocation، يجب إصلاح كل مسارات الحماية التي تسمح بالاستمرار عند فشلها. فشل `kill-switch` أو `risk authority` أو التحقق النهائي من SL يجب أن ينتج:

```text
SAFE_REJECT
```

ولا يجوز أن ينتج `allow trade` أو استمرارًا صامتًا. أخطاء التحليلات والـ dashboard يمكن أن تبقى non-fatal، لكن مكونات الحماية الأساسية يجب أن تكون fail-closed.

هذا الإصلاح هو أول commit تشغيلي، مع اختبار regression يثبت أن exception داخل `should_block_trade()` يمنع التنفيذ.

### 2.1 توحيد مسارات الاستراتيجيات

المسار الحالي يستخدم عقدًا موحدًا للاستراتيجيتين النشطتين SMC وDAILY عبر
`DecisionContext` و`unified_decide`. لم تعد هناك مسارات دخول مستقلة أخرى.

يجب أن تنتج الاستراتيجيتان النشطتان العقد نفسه:

```python
SignalSnapshot
```

ويحتوي على الأقل:

```text
signal_id
symbol
strategy
direction
signal_time
entry_reference
regime
session
structure
liquidity
atr
confidence
quality
execution_grade
mtf_alignment
raw_signal_reason
```

ثم تمر كل الاستراتيجيات عبر:

```text
SignalSnapshot
-> DecisionAuthority
-> PortfolioRiskAuthority
-> EntryPlan
-> ExitPlan
-> Execution
```

### 2.2 عقود بيانات واضحة

إنشاء نماذج/عقود واضحة بدل تمرير قواميس مختلفة بين الوحدات:

```text
SignalSnapshot
DecisionResult
RiskDecision
EntryPlan
ExitPlan
ExecutionResult
PositionState
ShadowOpportunity
```

كل عقد يجب أن يحمل `build_id` و`decision_snapshot_id`.

### 2.3 Decision Authority واحدة

يجب أن تكون هناك نقطة قرار واحدة تنتج حالات واضحة:

```text
REJECTED
WAIT_RETEST
WAIT_CONFIRMATION
APPROVED
EXECUTED
EXPIRED
CLOSED
```

لا تعتبر موافقات Phase 3 أو Final Brain في وضع Shadow موافقات تنفيذية.

يجب التفريق بين:

```text
DIRECTION_VALID
EXECUTION_NOT_READY
```

وبين:

```text
INVALID_SIGNAL
```

يجب ربط Phase 3 الحالي بهذه السلطة بدل إنشاء سلطة Shadow بديلة: Phase 3 يقدم evidence واقتراحًا استشاريًا، أما القرار التنفيذي النهائي فيصدر من Authority الموحدة فقط.

### 2.4 SL/TP مصدر حقيقة واحد

يظل `adaptive_sl_tp_engine` مصدرًا للسياق وATR فقط. يصبح `sl_tp_finalizer` مصدر الخطة النهائية الوحيدة.

المسار المقترح:

```text
adaptive_sl_tp_engine
-> structure_stop
-> target_selector
-> sl_tp_finalizer
-> trade_executor
```

بعد `sl_tp_finalizer` لا يجوز لأي وحدة إعادة حساب الأسعار أو المسافات.

### 2.5 بوابة تحقق اتصال المسار الحي

كل مرحلة تنفيذية لا تعتبر مكتملة بمجرد إنشاء ملف أو class. يجب أن تثبت كل مرحلة:

```text
implementation exists
+ live caller exists
+ runtime log proves invocation
+ focused regression test passes
+ no duplicate writer/decision path exists
```

يجب تنفيذ هذا الفحص في نهاية كل Phase، وليس تأجيله إلى مرحلة Demo. أي وحدة غير موصولة بالمسار الحي تبقى `NOT_WIRED` ولا تدخل في ادعاءات الجاهزية.

`account_scope.py` لا يدخل ضمن الأولويات الأولى إلا بعد إثبات أنه موصول بالمسار الحالي ويؤثر في نطاق الحساب/البيانات المقصود.

### 2.6 Position Manager واحد

هناك مسارات متعددة للتريلينج وTP. يجب إنشاء مدير موحد:

```text
core/position_manager.py
```

وهو الوحيد الذي يدير:

```text
TP1
TP2
partial close
break-even
trailing
-time exit
evidence invalidation
```

لا يسمح لمسارين مستقلين بإرسال `order_send` لتعديل نفس الصفقة.

كل تعديل SL يجب أن يكون monotonic:

```text
BUY: لا ينخفض SL
SELL: لا يرتفع SL
```

## 3. المرحلة الأولى: Risk Contract ومراجعة الحماية

### 3.1 حساب الخطر قبل الموافقة

يجب أن يعرف النظام الخطة النهائية قبل الموافقة:

```text
Build provisional entry/SL plan
-> calculate actual lot
-> calculate actual dollar risk
-> check daily/portfolio limits
-> approve or reject
-> send exact plan
```

لا يتم تقييم المخاطر قبل معرفة SL واللوت النهائيين.

### 3.2 حدود الحساب الحالي

للحساب الحالي البالغ تقريبًا `$1000`:

```text
SL_SOFT_LIMIT = $10
SL_HARD_LIMIT = $15
MAX_SL_DISTANCE_DOLLARS = $30  # safety ceiling only, not a target
```

`SL_HARD_LIMIT` هو حد استراتيجية الدخول الفعلي، بينما `MAX_SL_DISTANCE_DOLLARS` هو سقف أمان مطلق على مستوى التنفيذ. لا يجوز أن تستخدم طبقة adaptive أو retry قيمة `$30` كخيار طبيعي؛ إذا تجاوزت الخطة `$15` ترفض أو تنتظر Retest أفضل، ولا يصل التنفيذ إلى `$30` إلا كحاجز أخير يمنع قيمة أكبر بسبب خلل أو حالة طارئة.

القواعد:

- SL أقل من أو يساوي `$10`: يمر بعد باقي الفحوص.
- SL بين `$10` و`$15`: يحتاج جودة/تأكيدًا أقوى.
- SL أكبر من `$15`: انتظار دخول أفضل أو رفض الصفقة.
- لا يتم قص SL البنيوي بالقوة إلى مستوى غير صالح.
- لا يتم السماح بـ `$30` أو `$50` في مرحلة الاختبار الأولى.

### 3.3 Retry آمن

إذا رفض الوسيط المسافة:

```text
retry فقط حتى broker minimum
```

لكن بشرط عدم تجاوز:

```text
SL_HARD_LIMIT
MAX_SL_DISTANCE_DOLLARS
actual risk budget
```

إذا كان broker minimum أكبر من `SL_HARD_LIMIT`، لا يسمح retry بفتح الصفقة؛ لأن السقف المطلق ليس تصريحًا بتجاوز حد الاستراتيجية.

إذا تطلب الوسيط مسافة أكبر من الحدود، تكون النتيجة:

```text
SAFE_REJECT_BROKER_DISTANCE
```

### 3.4 Fail-closed للحماية

أخطاء التحليلات والـ dashboard يمكن أن تكون non-fatal، لكن أخطاء المكونات التالية يجب أن تمنع التداول:

```text
risk authority
loss limits
kill switch
SL validation
position limits
execution plan validation
```

## 4. المرحلة الثانية: Structural Adaptive SL

### 4.1 مصادر SL

بالترتيب:

1. آخر Swing صالح.
2. Order Block.
3. FVG أو منطقة السيولة.
4. ATR كاحتياطي فقط.

الصيغة:

```text
SL = invalidation level + noise buffer
```

### 4.2 Noise-Aware Stop

يتم حساب ضوضاء آخر 20 شمعة، مثل متوسط الذيول والحركات العكسية:

```text
noise_buffer = recent noise statistic
SL = structural invalidation + noise_buffer
```

السوق الهادئ يأخذ buffer أصغر، والسوق المزعج يأخذ buffer أكبر، لكن لا يتم تجاوز السقف المالي.

أسباب التسجيل:

```text
SL_STRUCTURE
SL_FALLBACK_ATR
SL_REJECTED_TOO_WIDE
SL_STRUCTURE_INVALID
```

## 5. المرحلة الثالثة: Entry Controller وRetest

### 5.1 Market Entry

يسمح بالدخول فقط إذا:

- Authority وافق.
- يوجد تأكيد بنيوي صالح.
- لا يوجد تعارض MTF مؤثر.
- الخطر الفعلي داخل الميزانية.
- يوجد هدف قابل للوصول.
- لا توجد حماية فعالة تمنع التداول.

### 5.2 Smart Delayed Entry

عند ظهور كسر أو إشارة قوية:

1. حفظ منطقة الكسر/Order Block/FVG.
2. انتظار رجوع السعر.
3. انتظار شمعة رفض أو تأكيد.
4. إلغاء الإشارة بعد `3-5` شموع.

إذا كان الاتجاه صحيحًا لكن الدخول الحالي سيئ، تكون الحالة:

```text
DIRECTION_VALID
WAIT_FOR_RETEST
```

ولا تتم مطاردة السعر.

### 5.3 Confirmation after favorable movement

يمكن استخدام تحرك صغير لصالح الإشارة مثل `0.2R` كتأكيد، لكن لا يسمح بالدخول المتأخر إذا أصبح السعر بعيدًا عن نقطة invalidation أو أصبح العائد المتاح غير منطقي.

## 6. المرحلة الرابعة: Target Selector وTP مستقل

### 6.1 فصل TP عن SL

لا تستخدم قاعدة إجبارية:

```text
TP = SL * 3
```

يختار `target_selector` أقرب مستوى منطقي من:

- Liquidity pool.
- Previous swing.
- FVG.
- Range boundary.
- Support/resistance.

### 6.2 Probability-Based Target

```text
احتمال وصول مرتفع -> TP قريب
احتمال متوسط -> TP متوسط
احتمال ضعيف -> رفض الصفقة
```

الإعدادات الأولية:

```text
TP1_MIN_RR = 0.8
TP2_TARGET_RR = 1.5 - 2.0
```

إذا كان أقرب هدف أقل من الحد المقبول:

```text
REJECT_TARGET_TOO_CLOSE
```

ولا يتم اختراع هدف بعيد لتحقيق RR نظري.

### 6.3 Regime-specific targets

```text
TRENDING:
    TP متوسط/كبير + runner + structure trailing

RANGING:
    TP قريب عند حدود النطاق

VOLATILE/CRISIS:
    حجم أصغر أو رفض الصفقة
```

## 7. المرحلة الخامسة: إدارة الصفقة

### 7.1 الخروج المرحلي

إذا كان الحجم والوسيط يسمحان:

```text
TP1: إغلاق 50% عند 0.8R - 1.0R
TP2: إغلاق 30% عند 1.5R - 2.0R
Runner: 20% مع trailing
```

بعد TP1:

```text
SL = entry + spread/cost buffer
```

إذا كان الحجم `0.01` ولا يسمح بالـ partial close:

```text
PARTIAL_EXIT_UNAVAILABLE_MIN_LOT
```

ولا يتم تنفيذ partial وهمي.

### 7.2 Dynamic Profit Lock

إذا:

```text
MFE >= 0.5R
```

ثم لم يحدث تقدم لعدد محدد من الشموع، يتم إغلاق جزء أو الخروج حسب regime.

### 7.3 Time Exit

بعد `5-8` شموع بلا تقدم:

```text
إذا MFE < 0.3R:
    EXIT_TIME_NO_PROGRESS
```

### 7.4 Evidence Invalidation

يعاد تقييم الصفقة كل شمعة:

- الاتجاه.
- السيولة.
- البنية.
- الزخم.
- السبريد.
- MTF conflict.

إذا فقدت الصفقة سبب دخولها:

```text
EXIT_EVIDENCE_INVALIDATED
```

ولا يتم توسيع SL لإنقاذها.

## 8. المرحلة السادسة: Opportunity Allocator

### 8.1 الهدف

بدل سؤال:

```text
هل توجد إشارة؟
```

يسأل النظام:

```text
هل هذه أفضل فرصة متاحة الآن وتستحق المخاطرة؟
```

وحدة مقترحة:

```text
core/opportunity_allocator.py
```

### 8.2 Opportunity Score

```text
Opportunity Score =
Edge
* Probability
* Market Space
* Execution Quality
* Regime Fit
```

لا يتم الدخول لمجرد تجاوز score عام؛ يجب أن تتوفر مساحة وهدف وخطر مقبول.

### 8.3 Allocation tiers

```text
فرصة عادية: 0.25R
فرصة جيدة: 0.50R
فرصة ممتازة: 0.75R
```

لا تزيد المخاطرة بسبب ثقة نظرية فقط. الزيادة تحتاج نتائج حقيقية كافية لنفس:

```text
strategy
session
regime
direction
entry_type
SL profile
TP profile
```

### 8.4 حالات اليوم

```text
SURVIVAL
NORMAL
OPPORTUNITY
PROTECTION
```

- `SURVIVAL`: بعد خسائر أو ظروف سيئة، تقليل أو إيقاف التداول.
- `NORMAL`: المخاطرة الأساسية.
- `OPPORTUNITY`: يسمح بفرص إضافية فقط عند Edge مثبت.
- `PROTECTION`: بعد ربح يومي، تقليل المخاطرة وحماية الربح.

### 8.5 Profit Lock

لا يجعل النظام هدف `$20/$50/$100` سببًا للإفراط في التداول.

بعد ربح يومي جيد:

- تقليل المخاطرة.
- قبول setups استثنائية فقط.
- منع إعادة معظم الربح للسوق.

## 9. المرحلة السابعة: Shadow Counterfactual

### 9.0 التكامل مع Phase 3 Shadow الحالي

المشروع يحتوي بالفعل على Phase 3 Shadow، بما فيه Portfolio Brain وStrategy DNA وFinal Brain وGold Context. لا يتم إنشاء نظام Shadow بديل معزول.

يظل لكل نظام سؤال مختلف:

```text
Phase 3:
هل كانت طبقة Shadow ستوافق أو ترفض القرار؟

Counterfactual:
ماذا حدث للسعر لو تم استخدام خطة دخول/SL/TP افتراضية؟
```

يرتبط السجلان عبر:

```text
signal_id
decision_snapshot_id
build_id
```

ويجب أن يظهر في التقرير الفرق بين:

```text
shadow_decision
counterfactual_market_result
actual_execution_result
```

لا تدخل نتائج Phase 3 أو Counterfactual في `adaptive_learning` أو sizing الحي قبل اعتماد صريح ومرور اختبار خارج العينة.

### 9.1 سجل الفرصة

ملف مقترح:

```text
data/analytics/shadow_opportunities.jsonl
```

ولا يكتب في ملفات الصفقات الحية أو adaptive state.

كل إشارة مرفوضة تحمل:

```text
signal_id
build_id
decision_snapshot_id
direction
strategy
entry_reference
virtual_sl
virtual_tp1
virtual_tp2
rejected_reason
spread
regime
session
```

### 9.2 متابعة النتيجة

يتم حساب:

```text
MAE خلال 5/10/20 شمعة
MFE خلال 5/10/20 شمعة
TP1 reached
TP2 reached
SL reached
expiry
counterfactual_result
```

التصنيفات:

```text
REJECTED_BUT_TP1_REACHED
REJECTED_AND_SL_WOULD_HAVE_HIT
REJECTED_NO_VALID_MOVE
REJECTED_TARGET_UNREALISTIC
```

لا تسجل هذه النتائج كصفقات حقيقية ولا تدخل في `adaptive_learning`.

### 9.3 Opportunity Cost Dashboard

يعرض:

```text
عدد الإشارات المرفوضة
عدد TP1 الافتراضية
عدد SL الافتراضية
نسبة الفرص الجيدة المرفوضة
أكثر سبب رفض تسبب في فرص ضائعة
```

ويقسم النتائج حسب strategy/session/regime/direction/rejection reason.

## 10. المرحلة الثامنة: Decision Ledger وTruth Attribution

يجب تسجيل دورة الحياة الكاملة:

```text
signal
-> authority
-> risk
-> entry
-> SL/TP
-> management
-> exit
-> result
```

كل سجل يرتبط بـ:

```text
BUILD_ID
signal_id
decision_snapshot_id
position_id
order_id
deal_id
```

ويجب التمييز بين:

```text
LIVE
PAPER
SHADOW
HISTORICAL
```

الهدف هو اكتشاف هل المشكلة كانت:

```text
إشارة سيئة
دخول سيئ
SL ضيق
TP بعيد
تنفيذ متأخر
رفض خاطئ
سبريد
```

لا يسمح النظام بتعديل استراتيجية تلقائيًا قبل نتائج كافية خارج العينة.

## 11. حالة البيانات والتعلم

يجب فصل ملفات الحالة إلى:

```text
live runtime state
shadow state
historical data
model registry
```

ولا يسمح للتاريخ القديم بإعادة تفعيل `loss_pause_guard` أو تغيير القرار الحالي.

كل تعلم جديد يجب أن يمر عبر:

```text
BUILD_ID filter
source filter
out-of-sample validation
minimum sample size
```

لا تستخدم نتائج Shadow في حجم اللوت أو قرارات Live إلا بعد اعتماد صريح واختبار منفصل.

## 12. إعدادات مقترحة مستقبلية

```python
ADAPTIVE_EXIT_ENABLED = True
RETEST_ENTRY_ENABLED = True
RETEST_MAX_BARS = 5

SL_SOFT_LIMIT_DOLLARS = 10.0
SL_HARD_LIMIT_DOLLARS = 15.0

TP1_MIN_RR = 0.8
TP1_CLOSE_PERCENT = 0.50
TP2_TARGET_RR = 1.7
TP2_CLOSE_PERCENT = 0.30
RUNNER_PERCENT = 0.20

TIME_EXIT_BARS = 8
TIME_EXIT_MIN_MFE_R = 0.30

SMART_DELAYED_ENTRY_ENABLED = True
DELAYED_ENTRY_MAX_BARS = 5
DELAYED_ENTRY_CONFIRMATION_R = 0.20
NOISE_LOOKBACK_BARS = 20

DYNAMIC_PROFIT_LOCK_ENABLED = True
PROFIT_LOCK_MIN_MFE_R = 0.50
PROFIT_LOCK_MAX_STALL_BARS = 3
RE_EVALUATE_OPEN_TRADE_ENABLED = True

COUNTERFACTUAL_SHADOW_ENABLED = True
OPPORTUNITY_COST_SHADOW_ENABLED = True
LIVE_PARTIAL_EXIT_ENABLED = False
```

هذه إعدادات تصميمية وليست تعليمات لتفعيل التداول.

## 13. الوحدات المقترحة

```text
core/decision_contracts.py
core/entry_controller.py
core/structure_stop.py
core/target_selector.py
core/adaptive_exit_controller.py
core/position_manager.py
core/time_exit_manager.py
core/shadow_counterfactual.py
core/opportunity_allocator.py
core/decision_ledger.py
```

الربط يكون مع الوحدات الحالية فقط بعد تحديد مصدر الحقيقة:

```text
main.py
core/fer3on_decision_authority.py
core/unified_decision.py
core/sl_tp_finalizer.py
core/trade_executor.py
core/strategy_runners.py
execution/tp_monitor.py
execution/multi_tp.py
```

## 14. خطة التنفيذ العملية

### Phase 0: Read-only architecture

- توثيق المسارات الفعلية.
- تثبيت العقود.
- لا تغيير في التداول.
- حصر Phase 3 Shadow الحالي ومصادر سجلاته.
- تحديد كل caller حي لكل وحدة قبل اعتبارها جاهزة.
- تأجيل `account_scope.py` حتى يثبت اتصاله بالمسار الحالي.

### Phase 0.1: Safety gate hardening

- إصلاح `kill-switch` من fail-open إلى fail-closed.
- جعل فشل `risk authority` أو SL validation ينتج `SAFE_REJECT`.
- إضافة regression tests للـ exception paths.
- تشغيل اختبار live-path smoke يثبت أن أمر التنفيذ لا يصل إلى `order_send` بعد فشل الحماية.

### Phase 1: Contracts and lifecycle ledger

- إضافة نماذج القرار والخطة.
- تسجيل دورة الحياة.
- اختبارات schema.

### Phase 2: Unified authority and risk

- تمرير كل الاستراتيجيات عبر القرار الموحد.
- نقل risk approval بعد حساب الخطر الفعلي.
- توثيق أن Phase 3 استشاري ولا يملك صلاحية تنفيذ.
- التأكد أن القرار النهائي الواحد يفسر سبب الرفض بدل ظهور `EXECUTE` ثم `KILL_SWITCH_BLOCK`.

### Phase 3: Single SL/TP finalization

- توحيد SL/TP في `sl_tp_finalizer`.
- إضافة `structure_stop` و`target_selector`.
- تقييد retry.

### Phase 4: Single position manager

- دمج TP monitor وtrailing وbreak-even.
- إضافة time exit وevidence invalidation.
- منع التعديل المتعارض.

### Phase 5: Shadow opportunities

- دمج السجل مع Phase 3 الحالي عبر `signal_id` و`decision_snapshot_id` و`build_id`، لا إنشاء Shadow pipeline منفصل.
- تسجيل الفرص المرفوضة.
- حساب MFE/MAE وTP1/TP2 الافتراضيين.
- بناء Opportunity Cost report.

### Phase 6: Smart entry and exit

- Retest Entry.
- Noise-Aware Stop.
- Probability-Based TP.
- Dynamic Profit Lock.

### Phase 7: Opportunity allocation

- ترتيب الإشارات.
- تخصيص المخاطرة.
- حالات اليوم وProfit Lock.

### Phase 8: Demo validation

- تشغيل Demo/Paper فقط.
- مقارنة كل مرحلة بالنظام الأساسي.
- لا يتم تفعيل المرحلة التالية إلا بعد نجاح الاختبارات.

## 15. الاختبارات المطلوبة

### اختبارات العقود

- كل استراتيجية تنتج `SignalSnapshot` صالحًا.
- كل قرار يحمل `decision_snapshot_id` و`build_id`.
- لا يتم خلط Shadow مع Live.

### اختبارات المخاطر

- رفض SL أكبر من `$15`.
- عدم تجاوز الحد اليومي أو portfolio exposure.
- retry لا يتجاوز hard cap.
- فشل risk component يؤدي إلى `SAFE_REJECT`.
- exception داخل kill-switch يؤدي إلى `SAFE_REJECT` ولا يصل إلى `order_send`.
- ظهور سبب نهائي واحد للرفض، دون تعارض بين `Final Decision` و`KILL_SWITCH_BLOCK`.

### اختبارات SL/TP

- structural SL صالح للشراء والبيع.
- عدم استخدام TP بعيد مصطنع.
- TP1 وTP2 يعتمدان على الخطة النهائية.
- `0.01 lot` لا ينفذ partial غير مدعوم.

### اختبارات Position Manager

- SL يتحرك في اتجاه الحماية فقط.
- لا يوجد تعديل مزدوج في نفس الدورة.
- time exit يعمل عند عدم التقدم.
- evidence invalidation يغلق أو يقلل التعرض حسب السياسة.

### اختبارات Shadow

- إشارة مرفوضة يمكن تتبعها لاحقًا.
- Shadow result لا يكتب في trades.csv.
- MAE/MFE محسوبان مع السبريد وترتيب SL/TP.
- الصفقة التاريخية لا تعاد معالجتها كصفقة جديدة.
- Phase 3 decision وCounterfactual result مرتبطان بنفس `signal_id` و`decision_snapshot_id`.

### اختبارات اتصال المسار الحي

- كل وحدة جديدة لها caller حي معروف.
- runtime log يثبت استدعاء الوحدة في المسار المتوقع.
- لا توجد وحدة جديدة غير موصولة يتم احتسابها كأنها مفعلة.
- كل Phase يمر بـ smoke test مستقل قبل الانتقال إلى المرحلة التالية.

### اختبارات المقارنة

مقارنة النظام الأساسي بكل مرحلة وفق:

```text
Profit Factor
Expectancy
Win rate
Average win/loss
MFE/MAE
Early stop-out rate
TP1 capture rate
Maximum drawdown
Opportunity cost
Overtrading
```

## 16. معايير النجاح

لا تعتبر أي مرحلة ناجحة بسبب صفقة واحدة أو حركة لاحقة للسعر.

يجب إثبات:

```text
Expectancy موجبة
Profit Factor > 1.1
عدم زيادة Max Drawdown
تحسن MFE/MAE
انخفاض الخروج المبكر
انخفاض الفرص الجيدة المرفوضة
عدم تجاوز المخاطر
ثبات النتائج خارج العينة
```

## 17. القيود الإلزامية

- لا يتم تعطيل `AUTHORITY`.
- لا يتم تعطيل `kill-switch`.
- لا يتم تعطيل `loss-pause-guard`.
- لا يتم اعتبار Shadow موافقة تنفيذية.
- لا يتم اعتبار Shadow ربحًا حقيقيًا.
- لا يتم توسيع SL لإنقاذ الصفقة.
- لا يتم رفع المخاطرة لتحقيق هدف يومي ثابت.
- لا يتم تشغيل partial close إذا كان الوسيط لا يدعمه.
- لا يتم تعلم قاعدة جديدة من عينة صغيرة أو من نفس بيانات الاختبار.

## الخلاصة

الترتيب الآمن والكامل هو:

```text
Contracts
-> Safety Gate Hardening
-> Unified Authority
-> Risk Contract
-> Single SLTP Finalizer
-> Single Position Manager
-> Decision Ledger
-> Shadow Counterfactual
-> Retest Entry
-> Probability TP
-> Profit Lock/Time Exit
-> Opportunity Allocator
-> Demo Validation
```

هذه الوثيقة تجمع كل الاقتراحات السابقة وتحوّلها إلى خارطة تنفيذ مرتبة. لا توجد أي تغييرات تشغيلية مفعّلة بمجرد حفظها.
