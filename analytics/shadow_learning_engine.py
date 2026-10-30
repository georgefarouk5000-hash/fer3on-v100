"""Analyze rejected signals only after their outcomes are resolved from candles."""

import json
import os
from pathlib import Path
from typing import Dict, List, Optional, Any
from collections import Counter, defaultdict
from datetime import datetime, timezone
from dataclasses import dataclass
import statistics


@dataclass
class RejectedSignal:
    """بيانات إشارة مرفوضة"""
    signal_id: str
    direction: str
    regime: str
    strategy: str
    confidence: float
    quality_score: float
    reject_reason: str
    gate: str
    sl_dist: float
    tp_dist: float
    session: str
    signal_time: str


@dataclass
class ShadowOutcome:
    """Outcome resolved against subsequent market candles."""
    signal_id: str
    outcome: str
    is_win: bool
    price_distance_pnl: float
    rr_ratio: float
    confidence_level: str  # A+, A, B+, B, C, D


class ShadowLearningEngine:
    """محرك التعلم من الإشارات المرفوضة"""
    
    def __init__(self):
        try:
            from core.settings import SHADOW_COUNTERFACTUAL_LOG_PATH
            self.rejected_file = Path(SHADOW_COUNTERFACTUAL_LOG_PATH)
            from core.settings import SHADOW_COUNTERFACTUAL_MIN_SAMPLES
            self.min_samples = max(1, int(SHADOW_COUNTERFACTUAL_MIN_SAMPLES))
        except Exception:
            self.rejected_file = Path(
                'data/analytics/shadow_counterfactual/rejected_shadow_2026-09-01-clean.jsonl'
            )
            self.min_samples = 100
        self.training_output = Path('data/analytics/shadow_learning/training_dataset.jsonl')
        self.insights_output = Path('data/analytics/shadow_learning/learning_insights.json')
        self.training_output.parent.mkdir(parents=True, exist_ok=True)
        
    def load_rejected_signals(self) -> List[Dict[str, Any]]:
        """قراءة جميع الإشارات المرفوضة"""
        if not self.rejected_file.exists():
            return []
        
        signals = []
        with open(self.rejected_file, 'r', encoding='utf-8') as f:
            for line in f:
                try:
                    signals.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
        return signals
    
    def analyze_rejection_reasons(self, signals: List[Dict]) -> Dict[str, Any]:
        """تحليل أسباب الرفض"""
        if not signals:
            return {
                'total_rejected': 0,
                'rejection_gates': {},
                'rejection_reasons': {},
                'avg_quality_rejected': 0.0,
                'avg_confidence_rejected': 0.0
            }
        
        gates = Counter()
        reasons = Counter()
        qualities = []
        confidences = []
        
        for signal in signals:
            gate = signal.get('gate') or signal.get('gate_stage', 'UNKNOWN')
            reason = signal.get('reject_reason', 'UNKNOWN')
            quality = signal.get('quality_score', 0.0)
            confidence = signal.get('confidence', 0.0)
            
            gates[gate] += 1
            reasons[reason] += 1
            qualities.append(quality)
            confidences.append(confidence)
        
        return {
            'total_rejected': len(signals),
            'rejection_gates': dict(gates.most_common()),
            'rejection_reasons': dict(reasons.most_common()),
            'avg_quality_rejected': statistics.mean(qualities) if qualities else 0.0,
            'avg_confidence_rejected': statistics.mean(confidences) if confidences else 0.0,
            'quality_distribution': {
                'min': min(qualities) if qualities else 0.0,
                'max': max(qualities) if qualities else 0.0,
                'median': statistics.median(qualities) if qualities else 0.0,
                'stdev': statistics.stdev(qualities) if len(qualities) > 1 else 0.0
            }
        }
    
    def resolved_rejected_signals(
        self,
        signals: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Exclude pending and virtual records; use candle-resolved rejections only."""
        resolved_outcomes = {
            'WIN', 'LOSS', 'LOSS_INTRABAR_AMBIGUOUS', 'TIMEOUT',
        }
        return [
            signal for signal in signals
            if isinstance(signal, dict)
            and signal.get('record_type', 'REJECTED_SHADOW') == 'REJECTED_SHADOW'
            and str(signal.get('outcome', '')).upper() in resolved_outcomes
            and ShadowLearningEngine.resolve_shadow_outcome(signal) is not None
        ]

    @staticmethod
    def resolve_shadow_outcome(signal: Dict[str, Any]) -> Optional[ShadowOutcome]:
        """Convert the counterfactual candle resolver's label into analysis data."""
        outcome_name = str(signal.get('outcome', '')).upper()
        if outcome_name not in {
            'WIN', 'LOSS', 'LOSS_INTRABAR_AMBIGUOUS', 'TIMEOUT',
        }:
            return None

        try:
            sl_dist = float(signal.get('sl_dist') or 0)
            tp_dist = float(signal.get('tp_dist') or 0)
            quality = float(signal.get('quality_score') or 0)
        except (TypeError, ValueError):
            return None
        if sl_dist <= 0 or tp_dist <= 0:
            return None

        if quality >= 85:
            confidence_level = 'A+'
        elif quality >= 75:
            confidence_level = 'A'
        elif quality >= 65:
            confidence_level = 'B+'
        elif quality >= 55:
            confidence_level = 'B'
        elif quality >= 45:
            confidence_level = 'C+'
        elif quality >= 35:
            confidence_level = 'C'
        else:
            confidence_level = 'D'

        return ShadowOutcome(
            signal_id=str(signal.get('signal_id', 'unknown')),
            outcome=outcome_name,
            is_win=outcome_name == 'WIN',
            price_distance_pnl=(
                tp_dist if outcome_name == 'WIN'
                else -sl_dist if outcome_name in {'LOSS', 'LOSS_INTRABAR_AMBIGUOUS'}
                else 0.0
            ),
            rr_ratio=tp_dist / sl_dist,
            confidence_level=confidence_level,
        )
    
    def extract_training_data(self, signals: List[Dict]) -> List[Dict[str, Any]]:
        """Extract labeled examples from outcomes already resolved against candles."""
        training_data = []
        
        for signal in signals:
            outcome = self.resolve_shadow_outcome(signal)
            if outcome is None:
                continue
            
            training_record = {
                'signal_id': signal.get('signal_id'),
                'direction': signal.get('direction'),
                'regime': signal.get('regime'),
                'strategy': signal.get('strategy'),
                'session': signal.get('session'),
                'confidence': signal.get('confidence'),
                'quality_score': signal.get('quality_score'),
                'reject_gate': signal.get('gate') or signal.get('gate_stage', 'UNKNOWN'),
                'reject_reason': signal.get('reject_reason'),
                'sl_dist': signal.get('sl_dist'),
                'tp_dist': signal.get('tp_dist'),
                'outcome': outcome.outcome,
                'outcome_bar': signal.get('outcome_bar'),
                'outcome_source': 'CANDLE_RESOLVER',
                'rr_ratio': outcome.rr_ratio,
                'observed_win': outcome.is_win,
                'outcome_price_distance_pnl': outcome.price_distance_pnl,
                'confidence_level': outcome.confidence_level,
                'learning_type': 'SHADOW',
                'extracted_at': datetime.now(timezone.utc).isoformat()
            }
            training_data.append(training_record)
        
        return training_data
    
    def generate_learning_insights(self, 
                                  rejection_analysis: Dict,
                                  training_data: List[Dict]) -> Dict[str, Any]:
        """توليد رؤى التعلم من البيانات"""
        if not training_data:
            return {}
        
        observed_wins = sum(1 for t in training_data if t['observed_win'])
        observed_win_rate = observed_wins / len(training_data)
        sample_count = len(training_data)
        ready = sample_count >= self.min_samples
        
        # تحليل توزيع الثقة
        confidence_dist = Counter(t['confidence_level'] for t in training_data)
        
        # تحليل الأداء حسب الـ regime
        regime_performance = defaultdict(list)
        for t in training_data:
            regime_performance[t.get('regime') or 'UNKNOWN'].append(t['observed_win'])
        
        regime_win_rates = {
            regime: sum(wins) / len(wins) if wins else 0.0
            for regime, wins in regime_performance.items()
        }
        
        # تحليل الأداء حسب الجودة
        high_quality = [t for t in training_data if float(t.get('quality_score') or 0) >= 75]
        low_quality = [t for t in training_data if float(t.get('quality_score') or 0) < 50]
        
        high_quality_wr = sum(1 for t in high_quality if t['observed_win']) / len(high_quality) if high_quality else 0.0
        low_quality_wr = sum(1 for t in low_quality if t['observed_win']) / len(low_quality) if low_quality else 0.0
        
        # التوصيات
        recommendations = []
        
        if ready and observed_win_rate > 0.50:
            recommendations.append({
                'priority': 'HIGH',
                'action': 'خفض معايير QUALITY_TRUST_DISABLED',
                'reason': f'الإشارات المرفوضة المحلولة لديها معدل نجاح مرصود ({observed_win_rate:.2%})',
                'impact': 'قد تزيد الأرباح'
            })
        
        if ready and high_quality_wr > low_quality_wr + 0.15:
            recommendations.append({
                'priority': 'HIGH',
                'action': 'تشديد معايير جودة الإشارات العالية',
                'reason': f'الإشارات عالية الجودة ({high_quality_wr:.2%}) أفضل من المنخفضة ({low_quality_wr:.2%})',
                'impact': 'تحسين نسبة الفوز الكلية'
            })
        
        # تحليل الأداء حسب الـ regime
        best_regime = max(regime_win_rates.items(), key=lambda x: x[1]) if regime_win_rates else None
        worst_regime = min(regime_win_rates.items(), key=lambda x: x[1]) if regime_win_rates else None
        
        if ready and best_regime and worst_regime and (best_regime[1] - worst_regime[1]) > 0.20:
            recommendations.append({
                'priority': 'MEDIUM',
                'action': f'تكييف استراتيجية السلوك حسب الـ regime',
                'reason': f'{best_regime[0]} ({best_regime[1]:.2%}) يعمل أفضل من {worst_regime[0]} ({worst_regime[1]:.2%})',
                'impact': 'تحسين الأداء في الأنظمة المختلفة'
            })
        
        return {
            'analysis_date': datetime.now(timezone.utc).isoformat(),
            'total_shadow_records': len(training_data),
            'sample_count': sample_count,
            'minimum_samples': self.min_samples,
            'ready_for_recommendations': ready,
            'observed_statistics': {
                'win_rate': observed_win_rate,
                'winning_signals': observed_wins,
                'average_outcome_price_distance': statistics.mean(
                    t['outcome_price_distance_pnl'] for t in training_data
                ),
                'avg_rr_ratio': statistics.mean(t['rr_ratio'] for t in training_data)
            },
            'confidence_distribution': dict(confidence_dist),
            'regime_performance': regime_win_rates,
            'quality_performance': {
                'high_quality_wr': high_quality_wr,
                'low_quality_wr': low_quality_wr,
                'delta': high_quality_wr - low_quality_wr
            },
            'rejection_analysis': rejection_analysis,
            'recommendations': recommendations
        }
    
    def save_training_data(self, training_data: List[Dict]) -> bool:
        """حفظ بيانات التدريب"""
        try:
            with open(self.training_output, 'w', encoding='utf-8') as f:
                for record in training_data:
                    f.write(json.dumps(record, ensure_ascii=False) + '\n')
            return True
        except Exception as e:
            print(f"❌ خطأ في حفظ بيانات التدريب: {e}")
            return False
    
    def save_insights(self, insights: Dict) -> bool:
        """حفظ الرؤى"""
        try:
            with open(self.insights_output, 'w', encoding='utf-8') as f:
                json.dump(insights, f, ensure_ascii=False, indent=2)
            return True
        except Exception as e:
            print(f"❌ خطأ في حفظ الرؤى: {e}")
            return False
    
    def run(self) -> Dict[str, Any]:
        """تشغيل محرك التعلم الكامل"""
        print("\n" + "="*70)
        print("🌑 Shadow Learning Engine - تحليل الإشارات المرفوضة")
        print("="*70)
        
        # 1. تحميل الإشارات المرفوضة
        print("\n1️⃣ تحميل الإشارات المرفوضة...")
        raw_signals = self.load_rejected_signals()
        signals = self.resolved_rejected_signals(raw_signals)
        print(
            f"   ✅ تم تحميل {len(raw_signals):,} سجل؛ "
            f"منها {len(signals):,} نتيجة محلولة بالشموع"
        )
        
        if not signals:
            print("   ⚠️ لا توجد نتائج شموع محلولة؛ لن يتم توليد توصيات")
            empty_insights = {
                'generated_at': datetime.now(timezone.utc).isoformat(),
                'status': 'insufficient_data',
                'sample_count': 0,
                'minimum_samples': self.min_samples,
                'ready_for_recommendations': False,
                'observed_statistics': {},
                'recommendations': [],
            }
            if not self.save_training_data([]) or not self.save_insights(empty_insights):
                return {
                    'status': 'persistence_error',
                    'signals_analyzed': 0,
                    'unresolved_signals': len(raw_signals),
                    'observed_win_rate': None,
                    'insights': empty_insights,
                }
            return {
                'status': 'insufficient_data',
                'signals_analyzed': 0,
                'unresolved_signals': len(raw_signals),
                'observed_win_rate': None,
                'insights': empty_insights,
            }
        
        # 2. تحليل أسباب الرفض
        print("\n2️⃣ تحليل أسباب الرفض...")
        rejection_analysis = self.analyze_rejection_reasons(signals)
        print(f"   ✅ Total Rejected: {rejection_analysis['total_rejected']:,}")
        print(f"   ✅ Avg Quality: {rejection_analysis['avg_quality_rejected']:.2f}")
        print(f"   ✅ Avg Confidence: {rejection_analysis['avg_confidence_rejected']:.2f}")
        print(f"   ✅ Top Gate: {list(rejection_analysis['rejection_gates'].items())[0]}")
        
        # 3. استخلاص بيانات التدريب
        print("\n3️⃣ استخلاص بيانات التدريب...")
        training_data = self.extract_training_data(signals)
        print(f"   ✅ تم استخلاص {len(training_data):,} سجل تدريب")
        
        # 4. توليد الرؤى
        print("\n4️⃣ توليد رؤى التعلم...")
        insights = self.generate_learning_insights(rejection_analysis, training_data)
        insights['status'] = 'success'

        win_rate = insights.get('observed_statistics', {}).get('win_rate', 0.0)
        print(f"   ✅ معدل النجاح المرصود بالشموع: {win_rate:.2%}")
        if not insights.get('ready_for_recommendations'):
            print(
                f"   ⚠️ العينة غير كافية للتوصيات: "
                f"{len(training_data)}/{self.min_samples}"
            )
        print(f"   ✅ عدد التوصيات: {len(insights.get('recommendations', []))}")
        
        # 5. حفظ البيانات
        print("\n5️⃣ حفظ البيانات والرؤى...")
        data_saved = self.save_training_data(training_data)
        insights_saved = self.save_insights(insights)
        if data_saved:
            print(f"   ✅ تم حفظ بيانات التدريب: {self.training_output}")
        if insights_saved:
            print(f"   ✅ تم حفظ الرؤى: {self.insights_output}")
        if not data_saved or not insights_saved:
            return {
                'status': 'persistence_error',
                'signals_analyzed': len(signals),
                'training_records': len(training_data),
                'observed_win_rate': win_rate,
                'insights': insights,
            }
        
        # 6. عرض التوصيات
        print("\n6️⃣ التوصيات الرئيسية:")
        for i, rec in enumerate(insights.get('recommendations', [])[:3], 1):
            print(f"   {i}. [{rec['priority']}] {rec['action']}")
        
        print("\n" + "="*70)
        print("✅ اكتمل تحليل Shadow Learning")
        print("="*70)
        
        return {
            'status': 'success',
            'signals_analyzed': len(signals),
            'unresolved_signals': len(raw_signals) - len(signals),
            'training_records': len(training_data),
            'observed_win_rate': win_rate,
            'insights': insights
        }


def should_apply_shadow_learning() -> bool:
    """Return whether enough candle-resolved rejected outcomes exist to analyze."""
    engine = ShadowLearningEngine()
    signals = engine.resolved_rejected_signals(engine.load_rejected_signals())
    return len(signals) >= engine.min_samples


if __name__ == '__main__':
    engine = ShadowLearningEngine()
    result = engine.run()
    
    # عرض الإحصائيات
    if result.get('status') == 'success':
        stats = result.get('insights', {}).get('observed_statistics', {})
        print(f"\n📊 ملخص الإحصائيات:")
        print(f"   • معدل النجاح: {stats.get('win_rate', 0.0):.2%}")
        print(f"   • متوسط نتيجة المسافة السعرية: {stats.get('average_outcome_price_distance', 0.0):.2f}")
        print(f"   • متوسط R:R: {stats.get('avg_rr_ratio', 0.0):.2f}")
