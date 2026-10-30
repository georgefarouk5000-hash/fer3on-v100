# FER3ON — account_id Tagging + SL Cap $15 + Retry Audit — 2026-08-28

**الحالة:** منفّذ ومتحقق منه محليًا (compile + import test + full suite + smoke test). لم يُشغَّل على حساب MT5 حي.

## 1) عمود account_id — نفس نمط build_id لمحور الحساب

### المشكلة
`core/build_scope.py` بيحمي من اختلاط بيانات نسخة كود قديمة، لكن مفيش حماية من اختلاط بيانات **حساب MT5 قديم** لو اتغيّر الحساب من غير ما البيلد يتغيّر — لأن build_id بتاع صفوف الحساب القديم يفضل مطابق للبيلد الحالي بالظبط (هو نفس الكود، حساب تاني بس).

### الإصلاح
- **`core/account_scope.py`**: إضافة `get_cached_account_id()` — نسخة مخزَّنة (cache) من رقم حساب MT5 كـstring، بترجع "" لو مش متاح. مُصمَّمة عشان تتنادى من كل صف بيتكتب من غير ما تعمل نداء MT5 منفصل لكل صف. `ensure_account_scope()` بتحدّث الكاش تلقائيًا.
- **`core/data_integrity.py`**: إضافة `"account_id"` لـ `AI_MEMORY_COLUMNS`، `HISTORY_COLUMNS`، و`FIELD_ALIASES`.
- **كتابة account_id في كل نقطة تسجيل صفقة**: `core/trade_logger.py` (trades.csv)، `core/ai_memory.py` (ai_memory.csv)، `core/mt5_history_sync.py` (نقطتين)، `brain/trade_dna.py::record_trade_dna()` (trade_dna_v2.json).
- **`core/build_scope.py`**: `is_current_build_row()` اتقسمت لـ `_is_current_build()` (نفس المنطق الأصلي بالحرف) + `_is_current_account()` جديدة، مع نفس فلسفة التراجع (backward compat): صف من غير account_id خالص (بيانات قديمة قبل الإضافة) **لا يُستبعد**. الاستبعاد بيحصل بس لو الصف *فيه* account_id صريح ومختلف عن الحالي.

### ليه الطريقة دي بالذات
- **تراجع كامل**: الـ141+1731 صف القديمة مالهاش account_id — هتفضل تتفلتر بنفس منطق build_id/التاريخ الحالي، من غير أي تغيير في سلوكها.
- **fail-safe لو الحساب مجهول**: لو مقدرناش نعرف الحساب الحالي (MT5 مش متصل) لكن الصف بيدّعي حساب معيّن، بنستبعد بدل ما نفترض تطابق — نفس فلسفة fail-closed المستخدمة في كل حماية تانية اتصلحت في المحادثة دي.
- **نقطة واحدة للفلترة**: بما إن كل الاستهلاك (history_learner, trade_dna, confidence_engine, self_optimizer, adaptive_weighting, master_brain, strategy_kill_switch) بيمر عبر `is_current_build_row`/`filter_current_build_rows`، إضافة الفحص هناك بس كفت — مفيش حاجة تانية احتاجت تتلمس.

### حاجة لقيتها ومعملتش فيها حاجة عمدًا
`core/mt5_history_sync.py` فيه نقطة تالتة بتكتب لـ"truth_layer" (نظام منفصل، مش من الثلاثة ملفات اللي كنا بنتكلم عنهم) وفيها `build_id=BUILD_ID` بردو من غير account_id. سيبتها لأنها مش من ضمن الملفات اللي طلبتها، لكن لو truth_layer ده بيتستخدم في قرار حي، يستاهل نفس المعالجة لاحقًا.

## 2) توحيد سقف SL على $15

`core/settings.py::MAX_SL_DISTANCE_DOLLARS` كان `30` لحساب ≥$500، بينما وثيقتين (Roadmap و"أفضل فكرة للـSL/TP") حددوا `$15` صراحةً لمرحلة الاختبار الحالية ("ممنوع السماح بـ$30 أو $50"). اتغيّر لـ`15` لكل الأحجام. **ده تغيير سلوك حقيقي**: صفقات بمسافة وقف بنيوية بين $15 و$30 كانت بتتقص لتناسب الحد الجديد بدل ما تتنفذ بمسافتها الكاملة، وممكن صفقات كانت بتعدي دلوقتي ترفض لو المسافة البنيوية أكبر من الحد الجديد.

## 3) فحص Retry — كان already متصلح

كنت مسجّلها "معلّق بالكامل" في آخر جرد. رجعت لـ`core/trade_executor.py::_cap_retry_growth()` ولقيتها **متصلحة فعلاً** (كومنت داخلي بيوثق نفس المخاوف بالحرف: *"a $30 gold stop becomes $48, silently breaking the MAX_SL_DISTANCE_DOLLARS contract"*). العامل الفعلي للتوسيع محدود بأقل قيمة من: النمو المطلوب، `ORDER_RETRY_MAX_WIDEN_FACTOR=1.30`، و`MAX_SL_DISTANCE_DOLLARS / المسافة الأصلية` — يعني بيستورد `MAX_SL_DISTANCE_DOLLARS` مباشرة، فتغيير البند (2) لـ$15 اتطبّق عليه تلقائيًا من غير أي تعديل إضافي. مفيش حاجة عملتها هنا غير التأكد والتوثيق.

## التحقق

- `py_compile` على كل الملفات المعدَّلة: نضيف.
- اختبار استيراد فعلي (`import core.build_scope, core.trade_logger, core.ai_memory, core.mt5_history_sync, brain.trade_dna, main` إلخ) — تأكيد عدم وجود circular imports.
- 6 اختبارات جديدة (`tests/test_build_scope_account_id.py`) — كلهم PASS.
- **3 أخطاء حقيقية اكتُشفت وأُصلحت أثناء التحقق نفسه** (شفافية كاملة، مش أخطاء مخفية):
  1. `get_cached_account_id` مش مستورد في `mt5_history_sync.py` — أضيف الاستيراد الناقص.
  2. `tests/test_cleanup_ai_memory.py` عندها نسخة مكررة يدويًا من AI_MEMORY_COLUMNS (نفس الخطأ اللي الاختبار ده بيحمي منه للسكريبت نفسه) — استبدلتها باستيراد من المصدر الحقيقي عشان متتكررش المشكلة تاني.
  3. `tests/test_strategy_kill_switch_build_filter.py` (من إصلاح سابق) كانت فيها تواريخ ثابتة مطلقة، بقت خارج نافذة الـ168 ساعة بعد مرور وقت حقيقي من وقت كتابتها — اتحوّلت لتواريخ نسبية لوقت التشغيل، مش هتتكسر تاني.
- السويت الكامل: **648 passed / 5 failed** (نفس الـ5 المعروفين، غير متعلقين).
- `scripts/smoke_test.py`: 59/59.

## الملفات المتأثرة

- `core/account_scope.py`, `core/data_integrity.py`, `core/trade_logger.py`, `core/ai_memory.py`, `core/mt5_history_sync.py`, `brain/trade_dna.py`, `core/build_scope.py` (معدَّلين)
- `core/settings.py` (معدَّل — MAX_SL_DISTANCE_DOLLARS)
- `tests/test_build_scope_account_id.py` (جديد)
- `tests/test_cleanup_ai_memory.py`, `tests/test_strategy_kill_switch_build_filter.py`, `tests/test_total_risk_cap_guard.py` (إصلاح fragility، بدون تغيير في الغرض المُختبَر)
- هذا الملف (جديد)
