# FER3ON — BRAIN-SCOPE Connect Patch (2026-08-20)

متابعة لتدقيق باتش BRAIN-SCOPE (2026-08-19). التدقيق لقى إن الفلترة اتبنت صح
في الخمس/الست ملفات، لكنها معزولة عن القرار الحي فعليًا. الباتش ده بيوصّل
الفلترة لمسار main.py الحقيقي، وبيقفل كل النقط اللي كانت لسه محتاجة تأكيد.

## المشكلة

باتش BRAIN-SCOPE (2026-08-19) وصف `master_score` بإنه بيتكوّن جوه
`core/brain_unified.py`. ده مش المسار الحي فعليًا: main.py (main.py:536)
بينادي على `brain/master_brain.py::get_master_score()` — ملف تاني تمامًا.
`core/brain_unified.py` مالوش أي مستدعي إنتاجي (بس `scripts/smoke_test.py`
و3 ملفات tests/testing).

`get_master_score()` كان عنده نسخته المحلية الخاصة، منفصلة تمامًا عن
الخمس ملفات المعدّلة:
- `_load_history_rows()` بتقرا `trades.csv` و`mt5_trade_history.csv` خام
  بـ `csv.DictReader`، من غير أي فلترة بالبيلد أو بالتاريخ.
- `history_score` و`memory_score` (60% من أوزان master_score) بيتحسبوا من
  الفنكشنز المحلية دي.
- `dna_score` = `(history_score + memory_score) / 2` — مش بينادي على
  `get_trade_dna_score()` الحقيقية خالص، رغم إنها متستوردة فوق الملف.

يعني بعد باتش BRAIN-SCOPE بالكامل، الـ master_score الحقيقي (اللي main.py
بيستخدمه فعلًا للقرار) فضل بيتغذى 100% من صفقات كل النسخ مخلوطة، **بالظبط
زي قبل الباتش** — رغم إن الخمس ملفات المعدّلة كانت شغالة صح ككود، بس معزولة
(imports ميتة: `get_trade_dna_score`, `find_similar_trades`,
`get_history_score` — صفر استدعاءات فعلية جوه `master_brain.py`).

## الإصلاح

### `brain/master_brain.py`

| التغيير | التفاصيل |
|---|---|
| `_load_history_rows()` | بقت بتفلتر المصدرين (`trades.csv`, `mt5_trade_history.csv`) عن طريق `core.build_scope.filter_current_build_rows()` — نفس الوحدة المركزية اللي باقي BRAIN-SCOPE بيستخدمها. كل مصدر بـ `date_field` مطابق للـ schema بتاعه (`trades.csv` → `date`, `mt5_trade_history.csv` → `close_time` — مش نفس الشكل) |
| `dna_score` | بقى بينادي فعليًا على `brain.trade_dna.get_trade_dna_score(strategy, market_regime, session)` بدل الـ placeholder المزيف `(history+memory)/2` |
| imports | اتشالت الـ imports الميتة (`get_trade_dna_display`, `find_similar_trades`, `get_history_score`) — `get_trade_dna_score` بقت مستخدمة فعليًا، و`find_similar_trades` بقت متستدعاة transitively من جواها |
| `source` field | اتغيّرت من `'live_csv'` لـ `'live_csv_build_filtered'` لتوضيح إنها بقت مفلترة (مفيش أي كود تاني بيتحقق من القيمة دي نصيًا — تغيير آمن) |

**قرار مقصود لم أنفذه:** التقرير اقترح بديل تاني ممكن لـ history_score:
استخدام `get_history_score()`/`analyze_history()` بدل الفنكشن المحلي.
اخترت عدم استخدامه لأنه بيحسب حاجة مختلفة فعليًا (نسبة ربح BUY مقابل SELL
على مستوى عام، مش لكل strategy/regime/session، ومحتاج معرفة اتجاه الصفقة
اللي `get_master_score()` مالوش parameter ليه أصلًا). بدل كده طبّقت الخيار
التاني اللي التقرير قدّمه بنفس الوزن: نفس الفلترة اتضافت مباشرة جوه
`_calculate_historical_wr()` و`_calculate_recent_memory()` (عن طريق
`_load_history_rows()`) من غير ما يتغيّر معناهم أو الـ signature بتاعهم.

### `tests/test_master_brain_build_id_fix.py` (جديد)
اختبار regression بنفس نمط `tests/test_quant_engine_build_id_fix.py`
الموجود أصلًا في المشروع:
- بيتأكد إن history_score/memory_score بتتجاهل صفوف بيلدات تانية.
- بيتأكد إن prior محايد (50.0) بيرجع لو مفيش أي صفوف من البيلد الحالي.
- بيتأكد إن dna_score بقى فعلًا مختلف عن `(history+memory)/2` ومبني على
  بيانات DNA حقيقية.
- بيتأكد إن dna_score بيرجع الـ prior المحايد (25.0) لو مفيش تطابقات من
  البيلد الحالي.
- اتأكد يدويًا إن الأربع اختبارات دول كانوا هيفشلوا (FAILED) على الكود
  الأصلي قبل الفيكس، وبيعدّوا (PASSED) بعده — تأكيد إنهم فعليًا بيغطوا
  نفس الـ bug، مش اختبار شكلي.

## النقط اللي كانت لسه محتاجة تأكيد — اتأكدت كلها

| النقطة | النتيجة |
|---|---|
| `tools/dedupe_adaptive_trades.py` | اتأكد إنه اتنفذ فعلًا: `adaptive_trades.jsonl` = 958 سطر فريد دلوقتي، `.bak` فيه 1007، إعادة التشغيل ما لقتش أي تكرار جديد (idempotent) |
| `legacy_untagged_quarantine.csv` | اتأكد العدد بالظبط: 57 صف، واتأكد إنهم مش موجودين في `trades.csv` (141 صف، صفر تذاكر فاضية) |
| `py_compile` على الملفات | اتأكد: الـ8 ملفات (الستة الأساسيين + `dedupe_adaptive_trades.py` + `expected_edge_gate.py` من الباتش الأول) كلهم سليمين، وكمان `master_brain.py` بعد التعديل |
| وسم البيلد الجديد الديناميكي | اتأكد: `trade_executor.py`, `trade_logger.py`, `mt5_history_sync.py` الثلاثة بيستوردوا `BUILD_ID` ديناميكيًا (`from core.settings import BUILD_ID`) ويكتبوها وقت فتح/قفل الصفقة. مفيش أي نسخة قديمة متجمدة من `'FER3ON-FINAL-build1'` في أي كود حي (موجودة بس جوه تعليق واحد). أي صفقة تتقفل من دلوقتي هتتوسم صح بـ `FER3ON-FINAL-build1-MERGED-rearch-cert6` |

## اختبار الانحدار (Regression) — صفر أعطال جديدة

- `scripts/smoke_test.py`: **59/59** قبل وبعد الفيكس — مطابق تمامًا.
- `scripts/v7_smoke_test.py`: **3 نجحوا / 4 فشلوا** قبل وبعد الفيكس — نفس
  الأربعة فشل بالظبط (T1, T2, T5, T7)، مش متعلقين بـ build_id أو
  master_brain، وموجودين في الكود الأصلي قبل أي لمسة مني (اتأكد بمقارنة
  نسخة أصلية غير معدّلة جنبًا لجنب).
- `pytest tests/ testing/`: **575 نجح / 5 فشل** قبل الفيكس → **579 نجح**
  (+4 اختبارات جديدة) / **نفس الـ5 فشل بالظبط** بعد الفيكس. صفر انحدار.

## اختبار وظيفي مباشر

على بيانات الديسك الحالية (كل الصفوف لسه من البيلد القديم
`FER3ON-FINAL-build1`، زي ما وثّق التدقيق):

```
get_master_score('SMC', 'RANGING', 'LONDON')
  history_score: 50.0   (prior محايد)
  memory_score : 50.0   (prior محايد)
  dna_score    : 25.0   (prior محايد)
```

مثال حقيقي للفرق: نفس القرار على `MICRO/TRENDING/ASIA` كان قبل الفيكس
بيرجع `history_score = 25.0` (محسوبة من 8 صفقات بيلد قديم فعليًا)، وبعد
الفيكس بيرجع `history_score = 50.0` (prior محايد صحيح، لأن صفر صفقات من
البيلد الحالي موجودة).

اختبار إضافي (sandbox معزول، من غير لمس بيانات المشروع الحقيقية): إضافة 9
صفقات تجريبية بعد الـ cutoff بالبيلد الحالي (6 ربح/3 خسارة) رجّعت
`history_score = memory_score = 66.67` بالظبط — يعني الفلترة مش بس بتستبعد
صح، كمان بتسمح بدخول البيانات الصح لما توجد، وصفقات الـ141 القديمة فضلت
مستبعدة تمامًا زي ما لازم، من غير أي تلوّث بين البيلدين.

## لسه مفتوح — قرار منتج، مش باگ برمجي

التدقيق لاحظ (واتأكد) إن `run_self_optimization()` (self_optimizer.py) و
`run_adaptive_weighting()` (adaptive_weighting.py) — رغم إن فلترتهم صح —
مالهمش أي نداء حي في الإنتاج: الأول بس من `scripts/smoke_test.py` (يدوي)،
والتاني بس تعليق ميت في `telegram_bot.py`
(`# /adapt → run_adaptive_weighting(...)`). النقطتين دول اتعمّدت ما
اتلمستش في الباتش ده لأنهم قرار منتج (إمتى/إزاي يتشغّلوا تلقائيًا؟ كل كام
صفقة؟ أمر تليجرام حقيقي مربوط؟) بيأثر على معايير المخاطرة في نظام بيتاجر
بفلوس حقيقية — قرار محتاج توجيه صريح، مش حاجة تُقرَّر من نفسها.

## الملفات المتأثرة بالباتش ده

- `brain/master_brain.py` (معدّل)
- `tests/test_master_brain_build_id_fix.py` (جديد)
