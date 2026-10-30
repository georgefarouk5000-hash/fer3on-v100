# اقتراحات إضافية ذكية لتحسين Entry وExit في XAUUSD

**الحالة:** أفكار تجريبية للتقييم - غير مفعّلة
**التاريخ:** 2026-08-21
**العلاقة:** اقتراح مكمل لـ `ADAPTIVE_ENTRY_EXIT_PROPOSAL.md`

## الهدف

توسيع تصميم الدخول والخروج بأفكار تقلل الدخول في نهاية الحركة، وتمنع الخروج المبكر أو انتظار أهداف بعيدة، مع إبقاء كل التغييرات في Shadow/Paper Testing قبل أي تفعيل حي.

## 1. Smart Delayed Entry

لا يتم الدخول فور ظهور الإشارة دائمًا. يتم الانتظار لأحد الشرطين:

- Retest لمنطقة الكسر أو Order Block أو FVG.
- أو تحرك السعر لصالح الإشارة بنسبة صغيرة مثل `0.2R` ثم تأكيد جديد.

إذا لم يحدث التأكيد خلال 3-5 شموع، تلغى الإشارة.

الهدف هو تحسين سعر الدخول وتقليل المسافة بين الدخول ومستوى إبطال الفكرة، وليس مطاردة السعر.

## 2. Noise-Aware Stop

يتم حساب ضوضاء السوق من آخر 20 شمعة، مثل متوسط الذيول والحركات العكسية.

```text
noise_buffer = متوسط الضوضاء الأخيرة
SL = structure invalidation level + noise_buffer
```

السوق الهادئ يأخذ buffer أصغر، والسوق المزعج يأخذ buffer أكبر، مع الالتزام دائمًا بسقف المخاطرة المالي.

إذا تجاوز SL السقف المالي، لا يتم قصه إلى مستوى غير صالح؛ يتم رفض الصفقة أو انتظار دخول أفضل.

## 3. Probability-Based Target

لا يتم فرض `RR=3` على كل الصفقات. يتم اختيار الهدف حسب المساحة واحتمال الوصول:

```text
احتمال وصول مرتفع -> TP قريب
احتمال وصول متوسط -> TP متوسط
احتمال وصول ضعيف -> لا دخول
```

مصادر الهدف:

- Liquidity pool.
- Previous swing.
- FVG.
- Range boundary.
- Support/resistance.

يجب أن يحقق TP1 حدًا أدنى قابلًا للقياس، مثل `0.8R`، وإلا تسجل الصفقة كـ `REJECT_TARGET_TOO_CLOSE`.

## 4. Dynamic Profit Lock

إذا تحركت الصفقة لصالحنا ثم توقفت:

```text
MFE >= 0.5R
ثم لا يوجد تقدم لعدة شموع
```

يتم إغلاق جزء أو الخروج الكامل حسب حجم الصفقة وحالة السوق، بدل انتظار SL أو TP النهائي.

## 5. Re-evaluation كل شمعة

بعد فتح الصفقة، يعاد تقييم الأدلة كل شمعة:

- الاتجاه.
- السيولة.
- البنية.
- الزخم.
- السبريد.
- التعارض بين الأطر الزمنية.

إذا انعكست الأدلة بدرجة جوهرية، يتم الخروج المبكر وتسجيل:

```text
EXIT_EVIDENCE_INVALIDATED
```

لا يسمح هذا النظام بتوسيع SL لإنقاذ صفقة فقدت سبب دخولها.

## 6. Regime-Specific Exit Profiles

### TRENDING

- هدف متوسط أو كبير.
- Runner صغير.
- Trailing خلف Swing.

### RANGING

- هدف قريب عند حدود النطاق.
- لا تنتظر امتدادًا ترنديًا غير موجود.
- خروج أسرع عند ضعف الزخم.

### VOLATILE أو CRISIS

- تقليل الحجم.
- أو رفض الصفقة.
- عدم توسيع SL بلا سقف.

## 7. فصل اتجاه الصفقة عن جودة التنفيذ

يمكن أن يكون الاتجاه صحيحًا لكن سعر الدخول سيئًا. لذلك يجب أن يدعم القرار حالة مستقلة:

```text
DIRECTION_VALID
EXECUTION_NOT_READY
WAIT_FOR_RETEST
```

هذا أفضل من اعتبار الحالة فشلًا كاملًا أو فتح الصفقة فورًا.

## 8. Shadow Counterfactual للفرص المرفوضة

لكل إشارة مرفوضة، يتم إنشاء سجل افتراضي يتابع:

- السعر النظري للدخول.
- MAE خلال 5/10/20 شمعة.
- MFE خلال 5/10/20 شمعة.
- هل تحقق TP1؟
- هل تحقق TP2؟
- هل تم ضرب SL الافتراضي؟
- سبب الرفض.
- السبريد التقريبي وقت الإشارة.

مثال تصنيف:

```text
REJECTED_BUT_TP1_REACHED
REJECTED_AND_SL_WOULD_HAVE_HIT
REJECTED_NO_VALID_MOVE
REJECTED_TARGET_UNREALISTIC
```

لا تسجل هذه النتائج كصفقات حقيقية أو كأرباح مؤكدة. هي بيانات تقييم فقط.

## 9. Opportunity Cost Dashboard

يضاف تقرير يوضح:

```text
عدد الإشارات المرفوضة
عدد الإشارات التي وصلت TP1 افتراضيًا
عدد الإشارات التي ضربت SL افتراضيًا
نسبة الفرص الجيدة المرفوضة
أكثر سبب رفض تسبب في فرص ضائعة
```

يتم تقسيم النتائج حسب:

- الاستراتيجية.
- الجلسة.
- regime.
- اتجاه BUY/SELL.
- سبب الرفض.

## 10. إعدادات مقترحة للتجربة

```python
SMART_DELAYED_ENTRY_ENABLED = True
DELAYED_ENTRY_MAX_BARS = 5
DELAYED_ENTRY_CONFIRMATION_R = 0.20

NOISE_LOOKBACK_BARS = 20
DYNAMIC_PROFIT_LOCK_ENABLED = True
PROFIT_LOCK_MIN_MFE_R = 0.50
PROFIT_LOCK_MAX_STALL_BARS = 3

RE_EVALUATE_OPEN_TRADE_ENABLED = True
RE_EVALUATE_INTERVAL_BARS = 1

OPPORTUNITY_COST_SHADOW_ENABLED = True
```

هذه الإعدادات اقتراحية فقط ولا تضاف إلى المسار الحي قبل الاختبار.

## 11. ترتيب التجارب

لا تجرب كل الأفكار معًا حتى يمكن معرفة سبب التحسن أو التراجع.

### التجربة A

Smart Delayed Entry فقط.

### التجربة B

Probability-Based TP فقط.

### التجربة C

Noise-Aware Stop فقط.

### التجربة D

Dynamic Profit Lock وTime Exit.

### التجربة E

المجموعة الأفضل من A-D بعد مقارنة النتائج.

## 12. معايير التقييم

يجب مقارنة كل تجربة بالنظام الحالي وفق:

```text
Profit Factor
Expectancy
Win rate
Average win
Average loss
MFE/MAE
Early stop-out rate
TP1 capture rate
Maximum drawdown
عدد الفرص المرفوضة الجيدة
```

لا تعتبر الفكرة ناجحة لمجرد أن السعر تحرك في الاتجاه بعد إشارة واحدة.

## 13. قيود إلزامية

- لا يتم تجاوز `AUTHORITY`.
- لا يتم تعطيل `kill-switch`.
- لا يتم تعطيل `loss-pause-guard`.
- لا يتم اعتبار Shadow trade صفقة حقيقية.
- لا يتم تنفيذ partial close إذا كان حجم `0.01` لا يسمح به الوسيط.
- لا يتم رفع SL لإنقاذ صفقة فقدت سببها.
- لا يتم توسيع SL إلى `$30` أو `$50` دون موافقة واختبار منفصل.

## الخلاصة

أقوى مجموعة أفكار للتجربة هي:

```text
Smart Delayed Entry
+ Noise-Aware Stop
+ Probability-Based TP
+ Dynamic Profit Lock
+ Regime-Specific Exit
+ Opportunity Cost Shadow Dashboard
```

هذه الوثيقة اقتراح إضافي فقط، ولا تغير سلوك البوت الحالي ولا تمنح موافقة على التداول الحقيقي.
