# اقتراح: Adaptive Entry and Exit Controller لـ XAUUSD

**الحالة:** اقتراح تصميم فقط - غير مفعّل
**التاريخ:** 2026-08-21
**النطاق:** Shadow/Paper Testing قبل أي تفعيل حي

## 1. المشكلة

التشغيل الحالي يربط مسافة الهدف بمسافة وقف الخسارة عبر `RR` ديناميكي. عند جعل SL قريبًا مثل `$15` أو `$20` قد يتم ضربه بسبب ضوضاء الذهب، وعند السماح بـ `$30` يكبر الهدف إلى مسافات مثل `$70-$90` فلا يتحقق غالبًا.

توجد مشكلة ثانية مستقلة: بعض الإشارات التحليلية الجيدة تُرفض عند بوابة القرار النهائية بسبب `AUTHORITY=NONE` و`STRATEGY_HARD_GATE`. لذلك لا يجوز اعتبار `SHADOW_APPROVE` موافقة تنفيذية أو تجاوز بوابات الحماية بدون قياس.

## 2. الهدف

بناء طبقة دخول وخروج متكيفة تحقق الآتي:

- وقف خسارة مبني على إبطال الفكرة وليس رقمًا ثابتًا فقط.
- سقف مالي صارم مناسب لحساب `$1000`.
- هدف مستقل عن SL، ومبني على أقرب سيولة/مستوى منطقي.
- خروج مرحلي عند توفر حجم يسمح بذلك.
- متابعة Shadow للصفقات المرفوضة لقياس الفرص الضائعة.
- عدم تجاوز Authority أو kill-switch أو loss-pause-guard.

## 3. قاعدة أمان أساسية

لا يتم تجاوز أو تعطيل:

```text
AUTHORITY=NONE
STRATEGY_HARD_GATE
QUALITY_TRUST_DISABLED
LOSS_PAUSE_GUARD
KILL_SWITCH
```

أي موافقة من Phase 3 أو Final Brain وهي في وضع Shadow تبقى استشارية فقط.

## 4. Entry Controller

### Market Entry

يسمح بالدخول فقط إذا تحققت كل الشروط التالية:

- Authority وافق.
- يوجد تأكيد بنيوي صالح مثل BOS أو Retest.
- لا يوجد تعارض MTF مؤثر.
- مسافة SL داخل الميزانية.
- يوجد هدف منطقي يحقق الحد الأدنى من العائد.
- جميع بوابات المخاطر تسمح بالتنفيذ.

### Retest Entry

عند ظهور كسر أو إشارة قوية، لا يتم الدخول فورًا دائمًا:

1. حفظ منطقة الكسر أو Order Block أو FVG.
2. انتظار رجوع السعر للمنطقة.
3. انتظار شمعة رفض/تأكيد في اتجاه الإشارة.
4. إلغاء الإشارة بعد 3-5 شموع إذا لم يحدث Retest.

لا تستخدم هذه الآلية لتجاوز Authority؛ هي فقط لتحسين سعر الدخول وتقليل مسافة SL.

## 5. Adaptive Structural SL

مصادر SL بالترتيب:

1. آخر Swing صالح.
2. Order Block.
3. FVG أو منطقة السيولة.
4. ATR كاحتياطي عند غياب البنية.

الصيغة العامة:

```text
SL = مستوى إبطال الفكرة + ATR buffer صغير
```

للحساب الحالي:

```text
SL_SOFT_LIMIT = $10
SL_HARD_LIMIT = $15
```

القواعد:

- SL أقل أو يساوي `$10`: يمر بعد فحص باقي الشروط.
- SL بين `$10` و`$15`: يحتاج جودة واتفاقًا أعلى.
- SL أكبر من `$15`: لا يتم قصه بالقوة؛ إما انتظار Retest أفضل أو رفض الصفقة.
- لا يسمح بـ `$30` أو `$50` في مرحلة الاختبار الحالية.

أسباب الرفض المسجلة:

```text
SL_REJECTED_TOO_WIDE
SL_STRUCTURE_INVALID
SL_FALLBACK_ATR
SL_CAPPED_BY_RISK
```

## 6. TP مستقل عن SL

لا تستخدم قاعدة إجبارية من الشكل:

```text
TP = SL * 3
```

يتم تحديد الهدف من أقرب مستوى منطقي:

- Liquidity pool.
- Previous swing.
- FVG.
- Range boundary.
- Support/resistance.

القواعد المقترحة:

```text
TP1_MIN_RR = 0.8
TP2_TARGET_RR = 1.5 - 2.0
```

إذا كان أقرب هدف لا يحقق `0.8R`، يتم رفض الصفقة بسبب:

```text
REJECT_TARGET_TOO_CLOSE
```

ولا يتم اختراع هدف بعيد فقط للحصول على RR مرتفع.

## 7. الخروج المرحلي

إذا سمح الوسيط والحجم بالإغلاق الجزئي:

```text
TP1: إغلاق 50% عند 0.8R - 1.0R
TP2: إغلاق 30% عند 1.5R - 2.0R
Runner: 20% مع trailing بنيوي
```

بعد TP1 يتم نقل SL إلى نقطة الدخول مع احتساب السبريد والتكاليف.

إذا كان حجم الصفقة `0.01` ولا يسمح بالإغلاق الجزئي:

- لا تنفذ partial close وهميًا.
- استخدم TP1 كاملًا أو trailing كاملًا.
- سجّل `PARTIAL_EXIT_UNAVAILABLE_MIN_LOT`.

## 8. Trailing وTime Exit

### Trending

Trailing خلف آخر Swing أو باستخدام مسافة مبنية على ATR.

### Ranging

الخروج عند حدود النطاق بدل trailing واسع.

### Volatile/Crisis

تقليل الحجم أو رفض الصفقة؛ لا يتم توسيع SL بلا حدود.

### Time Exit

إذا لم تحقق الصفقة تقدمًا بعد 5-8 شموع:

```text
إذا MFE < 0.3R -> خروج أو تقليل التعرض
```

سبب الخروج:

```text
EXIT_TIME_NO_PROGRESS
```

## 9. Shadow Counterfactual Tracking

كل إشارة مرفوضة تسجل وتراقب افتراضيًا:

- سعر الدخول النظري.
- SL وTP الافتراضيان.
- MAE خلال 5/10/20 شمعة.
- MFE خلال 5/10/20 شمعة.
- هل وصل TP1 أو TP2؟
- هل ضرب SL؟
- سبب الرفض.
- السبريد التقريبي.

شكل مقترح:

```json
{
  "signal_id": "...",
  "direction": "SELL",
  "entry_price": 0.0,
  "virtual_sl": 0.0,
  "virtual_tp1": 0.0,
  "virtual_tp2": 0.0,
  "rejected_reason": "AUTHORITY_NONE",
  "mfe": 0.0,
  "mae": 0.0,
  "tp1_reached": false,
  "tp2_reached": false,
  "sl_reached": false,
  "counterfactual_result": ""
}
```

لا تعتبر النتيجة ربحًا أو خسارة إلا بعد احتساب السبريد، وتنفيذ السعر، وترتيب SL/TP داخل الشمعة.

## 10. الوحدات المقترحة

```text
core/entry_controller.py
core/adaptive_exit_controller.py
core/structure_stop.py
core/shadow_counterfactual.py
core/time_exit_manager.py
```

يتم الربط مع:

```text
core/adaptive_sl_tp_engine.py
core/sl_tp_finalizer.py
core/trade_executor.py
core/strategy_runners.py
main.py
```

لا تعاد كتابة `adaptive_sl_tp_engine` بالكامل؛ يستخدم كمصدر ATR والسياق، بينما يتولى Controller قرار الدخول والخروج النهائي وفق البوابات.

## 11. إعدادات مقترحة

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
COUNTERFACTUAL_SHADOW_ENABLED = True
LIVE_PARTIAL_EXIT_ENABLED = False
```

هذه الإعدادات اقتراحية ولا تضاف إلى الإعدادات الفعالة إلا بعد اعتماد خطة الاختبار.

## 12. مراحل التنفيذ

### المرحلة الأولى: Shadow فقط

- تسجيل الإشارات المرفوضة.
- حساب النتائج الافتراضية.
- عدم تغيير التنفيذ الحقيقي.
- جمع 50-100 إشارة على الأقل.

### المرحلة الثانية: Paper/Demo

يسمح بالتنفيذ فقط عند تحقق:

```text
Authority approved
SL <= $15
TP1 >= 0.8R
Retest أو تأكيد سوقي صالح
لا يوجد Risk Guard فعال
```

### المرحلة الثالثة: Partial/Trailing

تفعيل الخروج المرحلي والتريلينج بعد اختبارهما على Demo والتأكد من دعم الوسيط للحجم الجزئي.

## 13. الاختبارات المطلوبة

- إشارة SELL مرفوضة ثم هبوط السعر.
- إشارة BUY مرفوضة ثم صعود السعر.
- رفض SL أكبر من `$15`.
- عدم قص SL البنيوي إلى مستوى غير صالح.
- TP1 قريب وTP2 مستقل.
- عدم اختراع TP بعيد لتحقيق RR مرتفع.
- عدم إعادة معالجة الإشارات القديمة.
- عدم تسجيل Shadow كصفقة حقيقية.
- عدم تنفيذ partial close عند `0.01 lot`.
- Time exit عند عدم وجود تقدم.
- عدم تجاوز `MAX_SL_DISTANCE_DOLLARS`.
- بقاء kill-switch وloss-pause-guard فعالين.

## 14. معيار النجاح

لا يعتبر التصميم ناجحًا لمجرد أن السعر تحرك بعد إشارة مرفوضة. يجب مقارنة النظام الحالي بالتصميم الجديد وفق:

```text
Profit Factor > 1.1
Expectancy موجبة
تحسن MFE/MAE
انخفاض الخروج المبكر
عدم زيادة Max Drawdown
عدم تجاوز الحد المالي
```

يجب عرض النتائج منفصلة لـ:

```text
النظام الحالي
النظام الجديد
الإشارات المرفوضة Shadow
```

## الخلاصة

التصميم المقترح هو:

```text
Retest Entry
+ Structure-Based Adaptive SL
+ Hard Monetary Risk Cap
+ TP مرحلي مستقل عن SL
+ Structure Trailing
+ Time Exit
+ Counterfactual Shadow Validation
```

هذا الملف اقتراح تصميم فقط. لا يعتبر موافقة على تفعيل التداول الحقيقي ولا يغير أي سلوك قائم قبل تنفيذ المراحل والاختبارات واعتماد النتائج.
