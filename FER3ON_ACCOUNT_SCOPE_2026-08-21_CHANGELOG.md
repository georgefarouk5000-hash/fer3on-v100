# FER3ON — Account Scope Fix — 2026-08-21

**الحالة:** منفّذ ومتحقق منه محليًا (compile + full test suite). لم يُشغَّل على حساب MT5 حي.
**يبني فوق:** commits `668c6da` / `9f676db` / `d6ed449` (georgegooo، 2026-08-21 02:42–02:50) اللي عملت reset يدوي لملفات الحالة ومنعت main.py من إعادة تشغيل آخر صف تاريخي كخسارة حية. الإصلاحات هنا **مكمّلة** لتلك الـcommits، مش بديلة عنها — الهدف إن نفس الـreset اليدوي ده يحصل تلقائيًا في المرة الجاية، ومفيش داعي يتكرر يدوي.

## المشكلة

1. **بيانات حساب/بيلد قديم بتتسرب لقرار حي جديد عبر ملفات حالة (state)، مش سجلات (logs).**
   `core/build_scope.py` بيحل المشكلة دي للسجلات (trades.csv, ai_memory.csv...) بالفلترة وقت القراءة. لكن `data/memory/loss_pause_guard.json` و `data/analytics/adaptive_state.json` عدادات حية (رقم واحد بيتغيّر عند كل صفقة تتقفل)، مش سجلات قابلة للفلترة — الفلترة مالهاش معنى هنا، والحل الوحيد reset فعلي عند تغيّر الحساب.

2. **`core/strategy_kill_switch.py::_read_recent_trades()` كانت بتقرا trades.csv بفلترة زمنية بس، من غير build_id.**
   بما إن trades.csv لسه فيه 141 صف قديم (تواريخهم لسه جوه نافذة الـ168 ساعة)، `should_block_trade()` كانت بتحسب weekly_pnl سالب لحساب جديد بصفر صفقات (SMC: -$79.74، MICRO: -$10.63)، وده كان بيفعّل شرط "exec_grade < A + أداء أسبوعي سالب" ويحظر صفقات B/C حتى لو الحساب نضيف تمامًا.

3. **`core/trade_executor.py` — استثناء جوه فحص الـkill-switch كان "non-fatal, allowing trade".**
   لو `should_block_trade()` رمت أي exception، الكود كان بيسمح بالصفقة بدل ما يمنعها — عكس مبدأ fail-closed لمكوّن حماية حرج.

## الإصلاح

### 1. ملف جديد: `core/account_scope.py`
- `get_current_account_login()`: بيقرا `mt5.account_info().login` دفاعيًا (بيرجع None لو MT5 غير متاح أو stub بيئة اختبار — من غير ما يفترض إن None يعني "حساب جديد").
- `ensure_account_scope()`: بيقارن الحساب الحالي بـfingerprint محفوظ في `data/analytics/account_fingerprint.json`.
  - نفس الحساب -> لا فعل.
  - حساب جديد/مختلف، والملفات فيها بيانات حقيقية -> أرشفة (نسخة كاملة، مش مسح) في `data/analytics/account_archive/<حساب_قديم>_<تاريخ>/` ثم reset لـ`loss_pause_guard.json` (عبر `core.loss_pause_guard.force_reset()` نفسها، مش نسخة مكررة من الشكل الافتراضي) و`adaptive_state.json` (بمسح الملف، لأن `adaptive_learning.load_state()` أصلاً بترجع DEFAULT_STATE لو الملف مش موجود).
  - حساب جديد لكن الملفات already نظيفة (زي الحالة دلوقتي، بعد الـreset اليدوي) -> تسجيل fingerprint بس، من غير أرشفة فاضية.
  - مفيش معلومات حساب خالص -> skip آمن، صفر تعديل.
- ميلمسش trades.csv / ai_memory.csv / mt5_trade_history.csv / trade_dna_v2.json / kill_switch_state.json — دول إما سجلات بتتفلتر بالـbuild_id (build_scope.py)، أو snapshot مُشتق بيتصلح من مصدره (نقطة 2 تحت).
- CLI مستقل: `python3 -m core.account_scope --status` / `--force`.

### 2. `core/strategy_kill_switch.py::_read_recent_trades()`
أُضيفت فلترة `core.build_scope.filter_current_build_rows(trades, date_field="date")` بعد الفلترة الزمنية الموجودة، بنفس نمط `master_brain.py`/`history_learner.py`/`trade_dna.py`. لو الاستيراد فشل لأي سبب، بيرجع لسلوك ما قبل الإصلاح (فشل الفلترة أهون من فشل الحماية كليًا).

هذا **الإصلاح الجذري** لمشكلة (2) — لأن `kill_switch_state.json` مجرد snapshot بيتولّد من نفس الدالة دي، مش مصدر بيانات مستقل. تصفيره يدويًا (زي ما حصل في commit `668c6da`) بيصلح العرض مؤقتًا، لكن أي استدعاء حي جديد لـ`should_block_trade()` كان هيعيد حساب نفس الرقم السالب من trades.csv تاني لحد ما الصفوف القديمة تخرج من نافذة الـ168 ساعة (~6 أيام كمان من تاريخه). بعد الإصلاح ده، المشكلة متحلوش بمرور الوقت بس — محلولة عند القراءة دايمًا.

### 3. `core/trade_executor.py`
الاستثناء بقى fail-closed: `return {'retcode': -1, 'comment': 'KILL_SWITCH_CHECK_FAILED_FAIL_CLOSED_<NoeType>'}` بدل الطباعة والمرور. المسار العادي (`should_block_trade()` رجّعت `block=True` صراحة) متأثرش خالص.

### 4. `main.py`
استدعاء `ensure_account_scope()` مرة واحدة في `main()`، بعد `connect_mt5()` وقبل `sync_mt5_history()` — قبل أي قراءة لملفات الحالة.

## التحقق

- `py_compile` على الأربعة ملفات (جديد + 3 معدّلة): نضيف.
- 11 اختبار جديد (`tests/test_account_scope.py` × 6، `tests/test_strategy_kill_switch_build_filter.py` × 3، `tests/test_trade_executor_fail_closed.py` × 2) — كلهم PASS، بما فيهم اختبار مباشر لسيناريو exec_grade الحقيقي (خسارة بيلد قديم $79.74 + exec_grade=B على حساب جديد -> block=False بعد الإصلاح)، واختبار تأكيدي إن خسارة بيلد حالي حقيقية لسه بتمنع (block=True).
- **مقارنة قبل/بعد على نفس السيرفر:**
  - قبل (baseline، بدون الإصلاحات الأربعة): `pytest tests/ testing/` -> **579 passed, 5 failed**.
  - بعد: **590 passed, 5 failed** (+11 بالظبط، نفس الـ5 فشل بالاسم — TP ladder pricing، quality floor mode string، adaptive architecture bypass — كلهم قبل هذا الإصلاح بشهور، ملهمش علاقة بالتغييرات دي).
  - `scripts/smoke_test.py`: 59/59 قبل وبعد.
  - `scripts/v7_smoke_test.py`: 3/7 قبل وبعد (نفس T7 الفاشل، معروف ومش متعلق).

## الملفات المتأثرة بالباتش ده (كل حاجة، بدون استثناء)

- `core/account_scope.py` (جديد)
- `core/strategy_kill_switch.py` (معدّل — `_read_recent_trades` فقط)
- `core/trade_executor.py` (معدّل — except block واحد فقط)
- `main.py` (معدّل — استدعاء واحد جديد في `main()`)
- `tests/test_account_scope.py` (جديد)
- `tests/test_strategy_kill_switch_build_filter.py` (جديد)
- `tests/test_trade_executor_fail_closed.py` (جديد)
- هذا الملف (جديد)

لا تغيير على أي ملف تاني، ولا على `core/strategy_kill_switch.py`'s المتعلقة بجلسات/regimes المحظورة (`SESSION_BLOCK_ENABLED` وغيره) — دي بقيت زي ما هي زي ما اتفقنا.

## لسه مفتوح — مش اتحل هنا عمدًا

لو غيّرت حساب MT5 من غير ما تغيّر البيلد (نفس الكود، حساب ديمو تاني)، `trades.csv` / `ai_memory.csv` / `trade_dna_v2.json` هيفضل فيهم صفوف الحساب القديم موسومة بـ**نفس** build_id الحالي — فلترة build_scope.py مش هتستبعدهم، لأنها بتفرّق بين نسخ الكود مش بين الحسابات. `account_scope.py` النهارده بيصفّر بس العدّادات الحية (loss_pause_guard، adaptive_state) عند تغيّر الحساب، ومش بيلمس السجلات دي.

لو ده سيناريو محتمل عندك (تجربة نفس الكود على أكتر من حساب ديمو)، الحل الكامل يحتاج إضافة عمود `account_id` للسجلات الثلاثة دي (بنفس أسلوب build_id تمامًا)، وده تغيير schema أكبر قصدًا مأجّلته لحد ما تأكد إنك محتاجه فعلاً.
