from __future__ import annotations

from collections import deque
from statistics import mean
from typing import Any


class AdaptiveWeightOptimizer:
    def __init__(self, window: int = 500) -> None:
        self.window = window
        self.history: dict[str, deque[float]] = {}

    def update(self, strategy_name: str, outcome_score: float) -> float:
        bucket = self.history.setdefault(strategy_name, deque(maxlen=self.window))
        bucket.append(float(outcome_score))
        avg = mean(bucket) if bucket else 0.5
        return round(max(0.05, min(1.5, 0.5 + avg)), 4)

    def weights(self) -> dict[str, float]:
        return {
            name: round(max(0.05, min(1.5, 0.5 + (mean(values) if values else 0.0))), 4)
            for name, values in self.history.items()
        }


class EvolutionEngine:
    def diagnose_trade(self, trade_record: dict[str, Any]) -> dict[str, Any]:
        """
        قيد صريح على عتبة "ATR was weak" (< 0.2): هذه عتبة ثابتة عامة غير
        مُعايرة لكل أصل (asset-specific) — لأصل مثل XAUUSD حيث ATR الحقيقي
        عادة عدة دولارات، هذه العتبة قلما تُفعَّل فعليًا حتى مع بيانات ATR
        حقيقية، وهذا سلوك متوقَّع وليس خللاً. الأهم: atr=None (بيانات غير
        مسجَّلة) يُستبعد عمدًا من هذا الفحص بدل معاملته كصفر حقيقي، تفاديًا
        لتشخيص كل الصفقات القديمة التي ينقصها هذا الحقل بأنها "ATR ضعيف" —
        وهو ما كان يحدث فعليًا قبل هذا الإصلاح عند تغذية الدالة ببيانات
        history_loader الحقيقية.
        """
        reasons = []
        atr = trade_record.get("atr")
        if atr is not None:
            try:
                if float(atr) < 0.2:
                    reasons.append("ATR was weak")
            except (TypeError, ValueError):
                pass
        if trade_record.get("liquidity_alignment") is False:
            reasons.append("Liquidity context was wrong")
        if trade_record.get("trend_changed"):
            reasons.append("Trend changed during trade")
        if trade_record.get("news_event"):
            reasons.append("News impact detected")
        if not reasons:
            reasons.append("No critical issue detected")
        return {
            "trade_id": trade_record.get("trade_id", "unknown"),
            "diagnosis": reasons,
            "recommended_actions": [
                "reduce weight when similar diagnosis repeats",
                "store the pattern in the knowledge graph",
            ],
        }

    def diagnose_recent(self, trade_records: list[dict[str, Any]]) -> dict[str, Any]:
        """
        يُشغّل diagnose_trade على دفعة صفقات حقيقية مُغلقة (وليس صفقة واحدة
        وهمية كما كان سابقًا في app.py) ويُجمّع تكرار كل سبب تشخيصي، مع
        تقسيم النتائج بين الصفقات الرابحة والخاسرة — لإعطاء صورة عامة عن
        أكثر أسباب الضعف تكرارًا بدل تشخيص صفقة واحدة معزولة كل دورة.

        هذا استقراء وصفي بسيط على العيّنة المُعطاة فقط، وليس تحققًا
        إحصائيًا صارمًا (راجع BACKTEST_VALIDITY_NOTICE.md).
        """
        if not trade_records:
            return {
                "sample_size": 0,
                "reason_counts": {},
                "reason_counts_on_losses": {},
                "most_common_reason": None,
                "most_common_loss_reason": None,
                "per_trade_sample": [],
            }

        per_trade = [self.diagnose_trade(r) for r in trade_records]
        counts: dict[str, int] = {}
        loss_counts: dict[str, int] = {}

        for record, diagnosis in zip(trade_records, per_trade):
            is_loss = str(record.get("result", "")).upper() == "LOSS"
            for reason in diagnosis["diagnosis"]:
                counts[reason] = counts.get(reason, 0) + 1
                if is_loss:
                    loss_counts[reason] = loss_counts.get(reason, 0) + 1

        most_common = max(counts.items(), key=lambda kv: kv[1])[0] if counts else None
        most_common_loss = max(loss_counts.items(), key=lambda kv: kv[1])[0] if loss_counts else None

        return {
            "sample_size": len(trade_records),
            "reason_counts": counts,
            "reason_counts_on_losses": loss_counts,
            "most_common_reason": most_common,
            "most_common_loss_reason": most_common_loss,
            "per_trade_sample": per_trade[-5:],
        }


class PatternDiscovery:
    def discover(
        self,
        trades: list[dict[str, Any]],
        min_samples: int = 5,
        min_win_rate: float = 60.0,
    ) -> list[dict[str, Any]]:
        """
        تعدين أنماط حقيقي من دفعة صفقات: يُجمّع الصفقات حسب توليفة الميزات
        (features) المشتركة بينها، ويحسب معدل النجاح الفعلي لكل توليفة على
        العيّنة المُعطاة. توليفة تظهر بعدد كافٍ من الصفقات (min_samples) وبمعدل
        نجاح أعلى من العتبة (min_win_rate) تُرشَّح لـ"candidate_for_auto_registration".

        هذا يستبدل الفحص القديم (تطابق توليفة واحدة ثابتة {high_atr,
        liquidity_sweep, pin_bar} مكتوبة يدويًا) باكتشاف فعلي متعدد
        التوليفات على أي دفعة صفقات حقيقية تُمرَّر له.

        قيد صريح: هذا إحصاء وصفي بسيط (descriptive) على عيّنة محدودة، وليس
        اختبار دلالة إحصائية (no significance testing / no correction for
        multiple comparisons). عدد صفقات صغير (قريب من min_samples) يعني
        ثقة منخفضة حتى لو بدا معدل النجاح مرتفعًا — راجع
        BACKTEST_VALIDITY_NOTICE.md قبل اعتماد أي نتيجة هنا في قرار حقيقي.
        """
        buckets: dict[frozenset, list[float]] = {}
        for trade in trades:
            features = trade.get("features", [])
            if not features:
                continue
            key = frozenset(features)
            success = float(trade.get("success", 0.0) or 0.0)
            buckets.setdefault(key, []).append(success)

        findings = []
        for feature_set, outcomes in buckets.items():
            sample_size = len(outcomes)
            if sample_size < min_samples:
                continue
            win_rate = (sum(outcomes) / sample_size) * 100.0
            if win_rate < min_win_rate:
                continue
            findings.append(
                {
                    "pattern": " + ".join(sorted(feature_set)),
                    "features": sorted(feature_set),
                    "sample_size": sample_size,
                    "success": round(win_rate, 2),
                    "status": "candidate_for_auto_registration",
                }
            )

        findings.sort(key=lambda f: (f["success"], f["sample_size"]), reverse=True)
        return findings
