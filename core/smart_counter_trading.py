# =============================================================================
# FER3ON — SMART COUNTER-TRADING ENGINE
# [FER3ON-FIX-2026-09-02]
# =============================================================================
# فكرة: عندما يكون هناك انحياز قوي (مثل 4:1 نحو SELL)، بدل محاربة الانحياز
# أو قبوله، استغله:
# - إذا 80%+ من الإشارات SELL → خذ بعض BUY عكسي بحجم صغير
# - استخدم trailing ضيق لتقليل الخطر
# - هذا يحول نقطة ضعف إلى نقطة قوة
#
# الخوارزمية:
# 1. احسب bias ratio (SELL/BUY)
# 2. إذا الانحياز > 3.0 (قوي جداً)، ثمّ:
#    a. احسب confidence للعكس (inverse confidence)
#    b. قلل الحجم: size = min_lot × 0.5 (نصف الحجم العادي)
#    c. زيّق الـ SL: sl = normal_sl × 0.6 (60% فقط)
#    d. حافظ على TP: tp = normal_tp (للربح التدريجي)
# 3. إذا الانحياز < 0.4 (انحياز عكسي قوي نحو BUY)، نفس المنطق معكوساً
# =============================================================================

from __future__ import annotations

import json
import os
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional, Dict, Any, Tuple


class SmartCounterTradingEngine:
    """
    محرك التداول العكسي الذكي
    يستغل الانحيازات القوية بدل محاربتها
    """
    
    def __init__(self, history_file: Optional[str] = None):
        # ✅ FIX [2026-09-02]: استخدم decisions.jsonl (جميع الإشارات) بدل rejected_shadow.jsonl (المرفوضة فقط)
        # السابق كان يحسب الانحياز من الإشارات المرفوضة فقط، مما ينتج عنه نسبة خاطئة تماماً
        self.history_file = history_file or 'data/analytics/decision_ledger/decisions.jsonl'
        self.counter_trades_log = Path('data/counter_trades_log.jsonl')
        self.counter_trades_log.parent.mkdir(parents=True, exist_ok=True)
    
    def calculate_signal_bias(self) -> Tuple[float, int, int]:
        """
        احسب نسبة الانحياز (SELL/BUY) من البيانات التاريخية
        
        Returns:
            (ratio, sell_count, buy_count)
            ratio = SELL/BUY (> 1 يعني انحياز نحو SELL)
        """
        try:
            if not Path(self.history_file).exists():
                return 1.0, 0, 0
            
            buy_count = 0
            sell_count = 0
            
            with open(self.history_file, 'r', encoding='utf-8') as f:
                for line in f:
                    if not line.strip():
                        continue
                    try:
                        record = json.loads(line)
                        direction = str(record.get('direction', 'UNKNOWN')).upper()
                        if direction == 'BUY':
                            buy_count += 1
                        elif direction == 'SELL':
                            sell_count += 1
                    except json.JSONDecodeError:
                        pass
            
            if buy_count == 0:
                return float('inf') if sell_count > 0 else 1.0, sell_count, buy_count
            
            ratio = sell_count / max(buy_count, 1)
            return ratio, sell_count, buy_count
        except Exception as e:
            print(f"⚠️ BIAS_CALCULATION_FAILED: {e}")
            return 1.0, 0, 0
    
    def should_apply_counter_trading(self) -> bool:
        """
        تحديد ما إذا كان يجب تطبيق التداول العكسي
        القرار: إذا الانحياز > 3.0 أو < 0.33 (انحياز قوي في أي اتجاه)
        """
        ratio, sell, buy = self.calculate_signal_bias()
        
        # انحياز قوي نحو SELL (ratio > 3.0) أو نحو BUY (ratio < 0.33)
        is_strong_bias = ratio > 3.0 or ratio < 0.33
        
        if is_strong_bias:
            direction = "SELL (4:1)" if ratio > 1 else "BUY (4:1)"
            print(f"📊 [COUNTER-TRADING] Strong bias detected: {direction} | ratio={ratio:.2f}:1")
        
        return is_strong_bias
    
    def calculate_inverse_confidence(self, market_conditions: Dict[str, Any]) -> float:
        """
        احسب ثقة التداول العكسي
        
        المنطق:
        - إذا كان الانحياز قوي جداً (4:1)، ثقة العكس عالية (0.6-0.8)
        - إذا الانحياز متوسط (2:1)، ثقة العكس متوسطة (0.4-0.6)
        - أبداً لا تتجاوز 0.8 (حتى في أقوى الانحيازات)
        """
        try:
            ratio, _, _ = self.calculate_signal_bias()
            
            # تحويل النسبة إلى ثقة (0-1)
            # ratio=3 → confidence=0.6
            # ratio=4 → confidence=0.75
            # ratio=5+ → confidence=0.8 (cap)
            
            if ratio > 1:
                # انحياز نحو SELL
                confidence = min(0.8, 0.3 + (ratio - 1.0) / 10.0)
            elif ratio < 1:
                # انحياز نحو BUY (معكوس)
                ratio_inverted = 1.0 / max(ratio, 0.01)
                confidence = min(0.8, 0.3 + (ratio_inverted - 1.0) / 10.0)
            else:
                # لا انحياز
                confidence = 0.0
            
            return round(confidence, 2)
        except Exception as e:
            print(f"⚠️ INVERSE_CONFIDENCE_CALC_FAILED: {e}")
            return 0.0
    
    def calculate_counter_position(
        self,
        original_signal: str,
        original_lot: float,
        original_sl: float,
        original_tp: float,
    ) -> Optional[Dict[str, Any]]:
        """
        احسب موقع العكس (counter position)
        
        Args:
            original_signal: 'BUY' أو 'SELL' (الإشارة الأصلية)
            original_lot: الحجم الأصلي
            original_sl: مسافة SL الأصلية
            original_tp: مسافة TP الأصلية
        
        Returns:
            dict مع تفاصيل الموقع العكسي، أو None إذا لا يجب التداول العكسي
        """
        if not self.should_apply_counter_trading():
            return None
        
        inverse_confidence = self.calculate_inverse_confidence({})
        if inverse_confidence < 0.4:
            return None
        
        # حدد الاتجاه العكسي
        counter_signal = 'SELL' if original_signal == 'BUY' else 'BUY'
        
        # قلل الحجم: حد أدنى 0.5× الحجم الأصلي
        # المنطق: التداول العكسي أكثر خطراً، لذا نستخدم حجماً أصغر
        counter_lot = round(original_lot * 0.5, 2)
        
        # زيّق الـ SL: 60% من SL الأصلي
        # المنطق: نقبل نقطة توقف أقرب للحد الأقصى للخسارة
        counter_sl = round(original_sl * 0.6, 2)
        
        # TP يبقى مثل الأصل (أو أقل قليلاً، 80%)
        # المنطق: نأخذ أرباح صغيرة متكررة
        counter_tp = round(original_tp * 0.8, 2)
        
        return {
            'enabled': True,
            'counter_signal': counter_signal,
            'counter_lot': counter_lot,
            'counter_sl': counter_sl,
            'counter_tp': counter_tp,
            'confidence': inverse_confidence,
            'reasoning': (
                f'Strong bias detected: {original_signal} dominant (ratio > 3.0) → '
                f'taking opportunistic {counter_signal} with reduced size/stops'
            ),
            'timestamp': datetime.now(timezone.utc).isoformat(),
        }
    
    def log_counter_trade(
        self,
        original_signal: str,
        counter_position: Dict[str, Any],
        execution_result: Optional[Dict[str, Any]] = None,
    ) -> None:
        """تسجيل تجارة عكسية في السجل"""
        try:
            record = {
                'timestamp': datetime.now(timezone.utc).isoformat(),
                'original_signal': original_signal,
                **counter_position,
            }
            if execution_result:
                record['execution'] = execution_result
            
            with open(self.counter_trades_log, 'a', encoding='utf-8') as f:
                f.write(json.dumps(record) + '\n')
        except Exception as e:
            print(f"⚠️ COUNTER_TRADE_LOG_FAILED: {e}")
    
    def get_counter_trading_summary(self) -> Dict[str, Any]:
        """احسب ملخص إحصائي للتجارات العكسية"""
        try:
            if not self.counter_trades_log.exists():
                return {
                    'total_counter_trades': 0,
                    'success_rate': 0.0,
                    'avg_confidence': 0.0,
                }
            
            total = 0
            wins = 0
            confidence_sum = 0.0
            
            with open(self.counter_trades_log, 'r', encoding='utf-8') as f:
                for line in f:
                    if not line.strip():
                        continue
                    try:
                        record = json.loads(line)
                        total += 1
                        
                        confidence_sum += float(record.get('confidence', 0) or 0)
                        
                        execution = record.get('execution', {})
                        if execution and execution.get('result') == 'WIN':
                            wins += 1
                    except json.JSONDecodeError:
                        pass
            
            success_rate = (wins / total * 100) if total > 0 else 0.0
            avg_confidence = (confidence_sum / total) if total > 0 else 0.0
            
            return {
                'total_counter_trades': total,
                'wins': wins,
                'success_rate': round(success_rate, 2),
                'avg_confidence': round(avg_confidence, 2),
            }
        except Exception as e:
            print(f"⚠️ COUNTER_SUMMARY_FAILED: {e}")
            return {
                'total_counter_trades': 0,
                'success_rate': 0.0,
                'avg_confidence': 0.0,
            }


# =============================================================================
# Global instance
# =============================================================================
_smart_counter_engine = SmartCounterTradingEngine()


def should_apply_smart_counter_trading() -> bool:
    """هل يجب تطبيق التداول العكسي الذكي؟"""
    return _smart_counter_engine.should_apply_counter_trading()


def get_counter_position(
    original_signal: str,
    original_lot: float,
    original_sl: float,
    original_tp: float,
) -> Optional[Dict[str, Any]]:
    """احسب موقع العكس"""
    return _smart_counter_engine.calculate_counter_position(
        original_signal, original_lot, original_sl, original_tp
    )


def log_counter_trade(
    original_signal: str,
    counter_position: Dict[str, Any],
    execution_result: Optional[Dict[str, Any]] = None,
) -> None:
    """تسجيل تجارة عكسية"""
    _smart_counter_engine.log_counter_trade(
        original_signal, counter_position, execution_result
    )


def get_counter_trading_summary() -> Dict[str, Any]:
    """احسب ملخص إحصائي"""
    return _smart_counter_engine.get_counter_trading_summary()
