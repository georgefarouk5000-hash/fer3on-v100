# FER3ON-MASR — Trading Intelligence Platform

## الملخص
هذه النسخة تضيف طبقة FER3ON-MASR فوق المشروع الحالي بدون حذف المحركات الأصلية.
الهدف هو تحويل FER3ON من Expert Advisor متقدم إلى منصة Trading Intelligence قابلة للتوسع.

## ما تم تنفيذه
1. Kernel موحد: config + event bus + registry + models + plugin manager
2. Market Intelligence Layer: trend / liquidity / structure / volatility / volume / momentum / session / news / sentiment / spread
3. Timeframe Intelligence: M1/M5/M15/H1/H4/D1/W1
4. Candle Intelligence: توقع احتمالات Bullish Engulf / Doji / Bearish Pin
5. Liquidity Intelligence: buy-side / sell-side / traps / sweep zones / best target
6. Range Intelligence: expected high/low/range/time/speed
7. Learning Center: فهرسة artifacts داخل learning_center/
8. Knowledge Graph: علاقات قابلة للحفظ والاستعلام
9. Strategy AI Agents: Daily / Swing / Scalp / SMC / Micro / News / Recovery
10. Executive Director: دمج قرارات الاستراتيجيات إلى خطة تنفيذ واحدة
11. Adaptive Weight Optimizer: تحديث أوزان الاستراتيجيات ديناميكيًا
12. Evolution Engine: تشخيص أسباب الخسارة أو الضعف
13. Pattern Discovery: اكتشاف أنماط قابلة للتسجيل تلقائيًا
14. Simulation Lab
15. Replay System
16. Explainability Service
17. Performance Optimizer
18. Multi-Asset readiness على مستوى config والعقود
19. API Layer descriptors
20. FER3ON OS foundation داخل حزمة fer3on_masr

## التشغيل
```bash
cd FER3ON-MASR
PYTHONPATH=. python3 -m fer3on_masr.app
```

## المخرجات
عند التشغيل يتم إنشاء:
- `data/fer3on_masr_demo_output.json`
- `data/masr_knowledge_graph.json`
- `learning_center/index.json`

## مبدأ الدمج
تم الحفاظ على أغلب الكود الحالي وإضافة طبقة تنظيمية جديدة تعتمد على بعض وحدات FER3ON الأصلية مثل ATR / market regime / session intelligence.

---

## تحديث: تفعيل حقيقي بدل الهياكل التجريبية (Real-Data Activation)

النقاط 4 و9 و13 أعلاه (Candle Intelligence، Strategy AI Agents، Pattern Discovery)
كانت هياكل عاملة لكن بمنطق تجريبي مبسّط جدًا. هذا التحديث يستبدلها بمنطق حقيقي
فعليًا يعمل، مع اختبارات جديدة (`tests/fer3on_masr/`، 40 اختبارًا، كلها ضمن
332 اختبارًا ناجحًا إجماليًا في المشروع):

1. **Candle Intelligence:** أصبح يفحص 24 نمط شمعة كلاسيكيًا فعليًا (Doji بأنواعه،
   Hammer/Hanging Man، Inverted Hammer/Shooting Star، Marubozu، Spinning Top،
   Engulfing، Harami، Piercing/Dark Cloud، Tweezer، Morning/Evening Star،
   Three Soldiers/Crows، Three Inside Up/Down) بتعريفات هندسية حقيقية (نسب
   جسم/فتيل/مدى)، بدل معادلة عامة واحدة على شمعة واحدة. الأزواج متطابقة الهندسة
   (Hammer/Hanging Man، Inverted Hammer/Shooting Star) تُميَّز عبر فحص الترند
   القصير السابق. كل الأنماط الآن مسجّلة أيضًا في
   `learning_center/patterns/candlestick_patterns.json`.
2. **Strategy AI Agents:** كل وكيل أصبح يقرأ مصدر بيانات مختلفًا فعليًا بدل
   `market_bias` المشترك: Daily→D1(+W1)، Swing→H4/H1، Scalp→M1/M5+تأكيد نمط
   شمعة، SMC→ملف السيولة+Structure Engine، Micro→M1 مع فلتر تقلّب وتفضيل
   RANGING، News→`news_bias` فعلي من اللقطة، Recovery→إحصاءات سجل حقيقي
   (anti-martingale: يُقلّص الحجم بعد سلسلة خسائر حقيقية، لا يُضاعفه).
3. **Evolution Engine / Pattern Discovery:** أصبحا يتغذيان من بيانات حقيقية
   عبر `fer3on_masr/learning/history_loader.py` (يقرأ فعليًا
   `data/history/trades.csv` و`data/memory/ai_memory.csv`، بنفس الدوال المستخدمة
   في core.data_integrity/core.ai_memory) بدل قاموس/قائمة ثابتة مكتوبة يدويًا في
   app.py. `PatternDiscovery.discover` أصبح يُعدِّن أي توليفة ميزات كافية العيّنة
   ومرتفعة النجاح، بدل فحص توليفة واحدة ثابتة.
4. **إصلاح صدق بيانات (اكتُشف أثناء الربط):** أعمدة `atr` و`news_score` في
   `ai_memory.csv` غير مسجَّلة فعليًا (صفر/فارغ) لنحو نصف الصفوف (news_score:
   أكثر من 99%). تم التمييز صراحة بين "لا بيانات" و"قراءة حقيقية بصفر" في
   `to_evolution_record`/`diagnose_trade` — وإلا كانت كل الصفقات ستُشخَّص خطأً
   بأن الـATR ضعيف ووجود تأثير إخباري لمجرد غياب التسجيل.
5. **ملاحظة حقيقية على البيانات الحالية:** لأحدث 200 صفقة مغلقة في
   `trades.csv`، حقول الإثراء (`choch_strength`, `liq_map_score`, `liq_map_dir`,
   `mtf_structural`, `atr`) في `ai_memory.csv` المقابلة فارغة بالكامل، و`exec_grade`
   موحّد على قيمة `SYNC` بدل الدرجات الحرفية (A+/B/...) المستخدمة في صفقات
   أقدم. لذا `pattern_discovery` قد يُرجع نتائج فارغة حاليًا بصدق (وهذا صحيح
   إحصائيًا مع هذه البيانات، وليس خللاً) — لإثراء الاكتشاف على النافذة الحالية
   يلزم تسجيل هذه الحقول وقت كتابة الصفقة في كود التنفيذ الحي (خارج نطاق هذه
   الطبقة).
6. **قاعدة المعرفة (learning_center):** أُضيف `books/07_advanced_technical_indicators_and_patterns.md`
   (فيبوناتشي، إليوت، بولينجر، ADX، إيشيموكو، باربوليك SAR، Point & Figure،
   أنماط شارت إضافية، أدوات حجمية) + cheatsheet عربي مرافق + رسمان أصليان
   (Fibonacci retracement، Elliott Wave structure). **لم يُنسخ أي نص أو صورة من
   كتاب جون ميرفي (أو أي كتاب آخر) حرفيًا** — المحتوى صياغة أصلية كاملة لمفاهيم
   عامة معروفة، بنفس مبدأ `books/06_classical_technical_analysis.md` الموجود
   مسبقًا. هذا المحتوى مرجعي/تعليمي مثل بقية ملفات learning_center، وغير موصول
   حاليًا بمحرك القرار الحي (`brain/knowledge_base.py` يقرأ من
   `data/knowledge/structured/*.json` فقط، وهو خارج نطاق هذا التحديث).

