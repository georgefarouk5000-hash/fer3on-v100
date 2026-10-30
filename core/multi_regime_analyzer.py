"""
🎯 Multi-Dimensional Regime Switching - تحديد السياق متعدد الأبعاد

Purpose:
  تحديد حالة السوق من خلال 5+ أبعاد بدلاً من بعد واحد فقط.
  كل dimensionون تساعد على اختيار الاستراتيجية المناسبة.

Architecture:
  Dimension 1: Trend Direction (UP/DOWN/FLAT)
  Dimension 2: Volatility Regime (HIGH/MEDIUM/LOW)
  Dimension 3: Volume Pattern (EXPANDING/CONTRACTING/NEUTRAL)
  Dimension 4: S/R Status (TESTING/HOLDING/BROKEN)
  Dimension 5: Time Context (ASIAN/LONDON/NEWYORK/etc)
  
  ↓
  
  Regime Combination → Strategy Selection:
    - Trending + strong trend → Use DAILY
    - Ranging + Low Vol + Contracting → Use SMC
    - Breakout + Expanding Volume → Use DAILY (trend following)
    - Choppy + Medium Vol → Use SMC with reduced sizing

Data Flow:
  rates data (OHLCV)
    ↓
  calculate_dimensions()
    ↓ (5 dimensions)
  combine_regimes()
    ↓
  recommend_strategy()
    ↓
  strategy_parameters.json (output)

Key Outputs:
  - primary_regime: الـ regime الأساسي
  - regime_strength: قوة الـ regime (0-1)
  - recommended_strategy: SMC or DAILY
  - confidence_score: ثقة التوصية
  - suggested_parameters: معاملات الاستراتيجية المقترحة
"""

import json
from pathlib import Path
from typing import Dict, List, Tuple, Optional, Any
from dataclasses import dataclass, asdict
from collections import Counter
import numpy as np
from datetime import datetime, timedelta


@dataclass
class Dimension:
    """بعد واحد من أبعاد تحليل الـ regime"""
    name: str
    value: str  # HIGH/LOW/MEDIUM/UP/DOWN/etc
    strength: float  # 0.0-1.0
    evidence: List[str]  # الأدلة على هذا البعد


@dataclass
class RegimeContext:
    """السياق الكامل متعدد الأبعاد"""
    timestamp: str
    trend_direction: Dimension
    volatility: Dimension
    volume_pattern: Dimension
    sr_status: Dimension
    time_context: Dimension
    primary_regime: str
    regime_strength: float
    recommended_strategy: str
    strategy_confidence: float
    suggested_parameters: Dict[str, Any]


class MultiDimensionalRegimeAnalyzer:
    """محلل الـ regime متعدد الأبعاد"""
    
    def __init__(self, rates_data: Optional[List[Dict]] = None):
        """
        Args:
            rates_data: بيانات الأسعار (OHLCV)
        """
        self.rates = list(rates_data) if rates_data is not None else []
        
        # معاملات التحليل
        self.trend_periods = [20, 50]  # EMA periods
        self.vol_periods = [14, 20]    # ATR/StdDev periods
        self.sr_lookback = 100         # نقاط البحث عن S/R

    @staticmethod
    def _field(row: Any, name: str, default: Any = 0) -> Any:
        """Read both dict-like bars and NumPy structured MT5 rows."""
        if isinstance(row, dict):
            return row.get(name, default)
        try:
            return row[name]
        except (IndexError, KeyError, TypeError, ValueError):
            return default
        
    def calculate_trend_direction(self) -> Dimension:
        """حساب اتجاه الاتجاه"""
        if len(self.rates) < max(self.trend_periods):
            return Dimension('trend', 'UNKNOWN', 0.0, ['بيانات ناقصة'])
        
        closes = np.array([self._field(r, 'close') for r in self.rates[-100:]])
        
        # حساب EMAs
        ema_20 = self._calculate_ema(closes, 20)
        ema_50 = self._calculate_ema(closes, 50)
        
        current_price = closes[-1]
        recent_high = np.max(closes[-20:])
        recent_low = np.min(closes[-20:])
        
        # تحديد الاتجاه
        if current_price > ema_20 > ema_50:
            direction = 'UP'
            strength = min(0.9, (current_price - ema_50) / (recent_high - recent_low)) if recent_high != recent_low else 0.5
        elif current_price < ema_20 < ema_50:
            direction = 'DOWN'
            strength = min(0.9, (ema_50 - current_price) / (recent_high - recent_low)) if recent_high != recent_low else 0.5
        else:
            direction = 'FLAT'
            strength = 0.3
        
        evidence = [
            f"Price={current_price:.2f}",
            f"EMA20={ema_20:.2f}",
            f"EMA50={ema_50:.2f}",
            f"Recent High/Low: {recent_high:.2f}/{recent_low:.2f}"
        ]
        
        return Dimension('trend', direction, strength, evidence)
    
    def calculate_volatility_regime(self) -> Dimension:
        """حساب نظام التذبذب"""
        if len(self.rates) < 20:
            return Dimension('volatility', 'UNKNOWN', 0.0, ['بيانات ناقصة'])
        
        closes = np.array([self._field(r, 'close') for r in self.rates[-100:]])
        
        # حساب ATR (Average True Range)
        atr = self._calculate_atr(self.rates[-100:], 14)
        close_price = closes[-1]
        
        # ATR كنسبة من السعر
        atr_ratio = atr / close_price if close_price > 0 else 0.0
        
        # تحديد النظام
        if atr_ratio > 0.02:  # > 2% من السعر
            regime = 'HIGH'
            strength = min(1.0, atr_ratio / 0.03)
        elif atr_ratio > 0.01:  # > 1%
            regime = 'MEDIUM'
            strength = 0.5
        else:
            regime = 'LOW'
            strength = 0.5
        
        evidence = [
            f"ATR={atr:.2f}",
            f"ATR% of Price={atr_ratio*100:.2f}%",
            f"Recent Volatility={'High' if regime == 'HIGH' else 'Normal' if regime == 'MEDIUM' else 'Low'}"
        ]
        
        return Dimension('volatility', regime, strength, evidence)
    
    def calculate_volume_pattern(self) -> Dimension:
        """حساب نمط الحجم"""
        if len(self.rates) < 20:
            return Dimension('volume', 'UNKNOWN', 0.0, ['بيانات ناقصة'])
        
        volumes = np.array([self._field(r, 'tick_volume') for r in self.rates[-20:]])
        
        if len(volumes) == 0 or np.all(volumes == 0):
            return Dimension('volume', 'NEUTRAL', 0.0, ['لا توجد بيانات حجم'])
        
        # حساب الاتجاه
        recent_vol = volumes[-5:].mean()
        older_vol = volumes[-20:-5].mean()
        
        if recent_vol > older_vol * 1.2:
            pattern = 'EXPANDING'
            strength = min(0.9, recent_vol / older_vol - 1.0)
        elif recent_vol < older_vol * 0.8:
            pattern = 'CONTRACTING'
            strength = min(0.9, 1.0 - recent_vol / older_vol)
        else:
            pattern = 'NEUTRAL'
            strength = 0.3
        
        evidence = [
            f"Recent Volume Avg={recent_vol:.0f}",
            f"Older Volume Avg={older_vol:.0f}",
            f"Ratio={recent_vol/older_vol:.2f}"
        ]
        
        return Dimension('volume', pattern, strength, evidence)
    
    def calculate_sr_status(self) -> Dimension:
        """حساب حالة الدعم والمقاومة"""
        if len(self.rates) < 50:
            return Dimension('sr_status', 'UNKNOWN', 0.0, ['بيانات ناقصة'])
        
        closes = np.array([self._field(r, 'close') for r in self.rates[-100:]])
        current = closes[-1]
        
        # البحث عن آخر قمة وقاع
        recent_high_idx = np.argmax(closes[-50:])
        recent_low_idx = np.argmin(closes[-50:])
        
        recent_high = closes[-50 + recent_high_idx]
        recent_low = closes[-50 + recent_low_idx]
        
        # المسافة من المستويات
        dist_to_high = recent_high - current
        dist_to_low = current - recent_low
        range_size = recent_high - recent_low
        
        # تحديد الحالة
        if dist_to_high < range_size * 0.1:  # قريب من المقاومة
            status = 'TESTING'
            strength = 0.7
            position = 'resistance'
        elif dist_to_low < range_size * 0.1:  # قريب من الدعم
            status = 'TESTING'
            strength = 0.7
            position = 'support'
        elif current > recent_high:
            status = 'BROKEN'
            strength = 0.8
            position = 'resistance'
        elif current < recent_low:
            status = 'BROKEN'
            strength = 0.8
            position = 'support'
        else:
            status = 'HOLDING'
            strength = 0.5
            position = 'middle'
        
        evidence = [
            f"Current={current:.2f}",
            f"Recent High={recent_high:.2f}",
            f"Recent Low={recent_low:.2f}",
            f"Position={position}"
        ]
        
        return Dimension('sr_status', status, strength, evidence)
    
    def calculate_time_context(self) -> Dimension:
        """حساب السياق الزمني"""
        now = datetime.utcnow()
        hour = now.hour
        
        # تحديد الجلسة
        if 22 <= hour or hour < 8:  # 10 PM - 8 AM UTC
            session = 'ASIAN'
        elif 8 <= hour < 12:  # 8 AM - 12 PM
            session = 'LONDON_START'
        elif 12 <= hour < 16:  # 12 PM - 4 PM
            session = 'LONDON_NEWYORK'
        else:  # 4 PM - 10 PM
            session = 'NEWYORK'
        
        # قوة السياق (جلسات متداخلة أقوى)
        if session == 'LONDON_NEWYORK':
            strength = 0.9
        elif session in ['LONDON_START', 'NEWYORK']:
            strength = 0.7
        else:
            strength = 0.5
        
        evidence = [f"Session={session}", f"Hour (UTC)={hour:02d}"]
        
        return Dimension('time_context', session, strength, evidence)
    
    def combine_regimes(self,
                       trend: Dimension,
                       volatility: Dimension,
                       volume: Dimension,
                       sr_status: Dimension,
                       time_context: Dimension) -> Tuple[str, float]:
        """دمج الأبعاد الخمسة لتحديد الـ regime الأساسي"""
        
        # إعطاء درجات للـ regime المحتملة
        regime_scores = {}
        
        # TRENDING (اتجاه قوي + حجم متوسع)
        if trend.value in ['UP', 'DOWN'] and trend.strength > 0.6:
            regime_scores['TRENDING'] = (trend.strength + volume.strength) / 2
        
        # RANGING (اتجاه مسطح + حجم منخفض)
        if trend.value == 'FLAT' or volatility.value == 'LOW':
            regime_scores['RANGING'] = 0.7
        
        # BREAKOUT (اتجاه مسطح + حجم متوسع + S/R مكسور)
        if sr_status.value == 'BROKEN' and sr_status.strength > 0.7:
            regime_scores['BREAKOUT'] = sr_status.strength
        
        # VOLATILE (تذبذب عالي)
        if volatility.value == 'HIGH':
            regime_scores['VOLATILE'] = volatility.strength
        
        # تحديد الأساسي
        if not regime_scores:
            primary = 'RANGING'
            strength = 0.5
        else:
            primary = max(regime_scores.items(), key=lambda x: x[1])[0]
            strength = min(1.0, regime_scores[primary])
        
        return primary, strength
    
    def recommend_strategy(self, regime: str, regime_strength: float, trend: Dimension) -> Tuple[str, float, Dict]:
        """توصيات الاستراتيجية"""
        
        if regime == 'TRENDING':
            if trend.value == 'UP' and trend.strength > 0.7:
                strategy = 'DAILY'  # Long-term trend following
                confidence = 0.8
            elif trend.value == 'DOWN' and trend.strength > 0.7:
                strategy = 'DAILY'  # Short-term trend following
                confidence = 0.8
            else:
                strategy = 'SMC'
                confidence = 0.6
        
        elif regime == 'RANGING':
            strategy = 'SMC'
            confidence = 0.7
        
        elif regime == 'BREAKOUT':
            strategy = 'DAILY'  # Breakout following
            confidence = 0.75
        
        elif regime == 'VOLATILE':
            strategy = 'SMC'
            confidence = 0.65
        
        else:
            strategy = 'SMC'  # Default
            confidence = 0.5
        
        # تحديد المعاملات
        params = {
            'strategy': strategy,
            'risk_percent': 0.5 if confidence > 0.7 else 0.3,
            'max_trades': 5 if regime == 'RANGING' else 3,
            'tp_multiplier': 2.0 if regime == 'BREAKOUT' else 1.5,
            'sl_multiplier': 1.0 if regime == 'VOLATILE' else 0.8,
            'min_confidence': 55 if confidence > 0.7 else 65
        }
        
        return strategy, confidence, params
    
    def analyze(self) -> RegimeContext:
        """تشغيل التحليل الكامل"""
        trend = self.calculate_trend_direction()
        volatility = self.calculate_volatility_regime()
        volume = self.calculate_volume_pattern()
        sr_status = self.calculate_sr_status()
        time_context = self.calculate_time_context()
        
        primary_regime, regime_strength = self.combine_regimes(
            trend, volatility, volume, sr_status, time_context
        )
        
        recommended_strategy, confidence, params = self.recommend_strategy(
            primary_regime, regime_strength, trend
        )
        
        return RegimeContext(
            timestamp=datetime.utcnow().isoformat(),
            trend_direction=trend,
            volatility=volatility,
            volume_pattern=volume,
            sr_status=sr_status,
            time_context=time_context,
            primary_regime=primary_regime,
            regime_strength=regime_strength,
            recommended_strategy=recommended_strategy,
            strategy_confidence=confidence,
            suggested_parameters=params
        )
    
    @staticmethod
    def _calculate_ema(data: np.ndarray, period: int) -> float:
        """حساب EMA"""
        if len(data) < period:
            return np.mean(data)
        
        multiplier = 2 / (period + 1)
        ema = np.mean(data[:period])
        
        for value in data[period:]:
            ema = value * multiplier + ema * (1 - multiplier)
        
        return ema
    
    @staticmethod
    def _calculate_atr(rates: List[Dict], period: int) -> float:
        """حساب ATR"""
        if len(rates) < period:
            return 0.0
        
        tr_list = []
        for i in range(1, len(rates)):
            h = MultiDimensionalRegimeAnalyzer._field(rates[i], 'high')
            l = MultiDimensionalRegimeAnalyzer._field(rates[i], 'low')
            c = MultiDimensionalRegimeAnalyzer._field(rates[i-1], 'close')
            
            tr = max(h - l, abs(h - c), abs(l - c))
            tr_list.append(tr)
        
        return np.mean(tr_list[-period:]) if tr_list else 0.0
    
    def to_dict(self, context: RegimeContext) -> Dict:
        """تحويل النتيجة إلى قاموس"""
        return {
            'timestamp': context.timestamp,
            'trend': {
                'direction': context.trend_direction.value,
                'strength': round(context.trend_direction.strength, 3),
                'evidence': context.trend_direction.evidence
            },
            'volatility': {
                'regime': context.volatility.value,
                'strength': round(context.volatility.strength, 3),
                'evidence': context.volatility.evidence
            },
            'volume': {
                'pattern': context.volume_pattern.value,
                'strength': round(context.volume_pattern.strength, 3),
                'evidence': context.volume_pattern.evidence
            },
            'sr_status': {
                'status': context.sr_status.value,
                'strength': round(context.sr_status.strength, 3),
                'evidence': context.sr_status.evidence
            },
            'time_context': {
                'session': context.time_context.value,
                'strength': round(context.time_context.strength, 3)
            },
            'primary_regime': context.primary_regime,
            'regime_strength': round(context.regime_strength, 3),
            'recommended_strategy': context.recommended_strategy,
            'strategy_confidence': round(context.strategy_confidence, 3),
            'suggested_parameters': context.suggested_parameters
        }


if __name__ == '__main__':
    # مثال على الاستخدام
    analyzer = MultiDimensionalRegimeAnalyzer()
    result = analyzer.analyze()
    
    print("\n" + "="*70)
    print("🎯 Multi-Dimensional Regime Analysis")
    print("="*70)
    
    output = analyzer.to_dict(result)
    print(json.dumps(output, indent=2, ensure_ascii=False))
