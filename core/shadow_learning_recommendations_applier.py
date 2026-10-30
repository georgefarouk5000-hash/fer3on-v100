#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
🌑 Shadow Learning Recommendations Applier
تطبيق توصيات Shadow Learning بشكل تدريجي وآمن

التوصيات:
  1. [HIGH] خفض QUALITY_TRUST_DISABLED threshold من X إلى X-10
  2. [HIGH] تشديد معايير جودة الإشارات العالية

الاستراتيجية:
  - البداية: مرحلة المراقبة (Monitoring Phase) - لا تغييرات بعد
  - الأسبوع 1: تفعيل QUALITY_SCORE_TRUST مع مراقبة 50+ تجارة
  - الأسبوع 2+: خفض threshold تدريجياً بـ 2-3 نقاط
  - الشهر: تحليل النتائج وتعديل نهائي
"""

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Any
import logging
import sys
import io

# تعيين stdout إلى UTF-8
if sys.stdout.encoding != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# إعدادات التطبيق التدريجي
GRADUAL_ROLLOUT_CONFIG = {
    "phase_1": {
        "name": "Monitoring Phase (Week 0)",
        "duration_days": 7,
        "actions": [
            "Monitor Shadow Learning insights",
            "No quality score changes yet",
            "Track execution_quality baseline"
        ],
        "status": "IN_PROGRESS"
    },
    "phase_2": {
        "name": "Soft Enablement (Week 1)",
        "duration_days": 7,
        "actions": [
            "Enable QUALITY_SCORE_TRUST with 30% apply rate",
            "Monitor Win Rate (target: maintain 64%+)",
            "Measure impact on SELL/BUY ratio"
        ],
        "quality_threshold_adjustment": 0,
        "apply_rate": 0.3,
        "status": "PENDING"
    },
    "phase_3": {
        "name": "Progressive Reduction (Week 2-3)",
        "duration_days": 14,
        "actions": [
            "Gradually reduce QUALITY_TRUST_DISABLED threshold",
            "Reduction pattern: -2 points every 3 days",
            "Target: -10 points total",
            "Monitor win rate after each reduction"
        ],
        "quality_threshold_reduction_schedule": [
            {"day": 1, "reduction": -2, "cumulative": -2},
            {"day": 4, "reduction": -2, "cumulative": -4},
            {"day": 7, "reduction": -2, "cumulative": -6},
            {"day": 10, "reduction": -2, "cumulative": -8},
            {"day": 13, "reduction": -2, "cumulative": -10},
        ],
        "apply_rate": 1.0,
        "status": "PENDING"
    },
    "phase_4": {
        "name": "Tightening High-Quality Standards (Week 4+)",
        "duration_days": 14,
        "actions": [
            "Increase confidence requirement for high-quality signals",
            "Boost risk multiplier for 75+ quality scores",
            "Apply stricter NEWYORK session floor"
        ],
        "high_quality_confidence_floor": 65,
        "high_quality_risk_multiplier": 1.25,
        "newyork_quality_floor_adjustment": 5,
        "status": "PENDING"
    }
}

class ShadowLearningRecommendationsApplier:
    """تطبيق توصيات Shadow Learning بشكل آمن وتدريجي"""
    
    def __init__(self, project_root: str = "."):
        self.project_root = Path(project_root)
        self.data_dir = self.project_root / "data" / "analytics" / "shadow_learning"
        self.config_dir = self.project_root / "config"
        self.log_file = self.project_root / "logs" / "shadow_learning_application.log"
        self.log_file.parent.mkdir(parents=True, exist_ok=True)
        
        self._setup_logging()
        self.logger = logging.getLogger("ShadowLearningApplier")
    
    def _setup_logging(self):
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s | %(name)s | %(levelname)s | %(message)s',
            handlers=[
                logging.FileHandler(self.log_file),
                logging.StreamHandler()
            ]
        )
    
    def get_current_phase(self) -> Dict[str, Any]:
        """الحصول على المرحلة الحالية من الدورة التدريجية"""
        phase_start_file = self.config_dir / "phase_start_date.json"
        
        if not phase_start_file.exists():
            # البداية من Phase 1
            start_date = datetime.now()
            phase_start_file.parent.mkdir(parents=True, exist_ok=True)
            with open(phase_start_file, 'w', encoding='utf-8') as f:
                json.dump({
                    "start_date": start_date.isoformat(),
                    "current_phase": "phase_1"
                }, f, indent=2)
            return ("phase_1", start_date)
        
        with open(phase_start_file, 'r', encoding='utf-8') as f:
            config = json.load(f)
        
        start_date = datetime.fromisoformat(config["start_date"])
        days_elapsed = (datetime.now() - start_date).days
        
        # تحديد المرحلة بناءً على الأيام المنقضية
        if days_elapsed < 7:
            current_phase = "phase_1"
        elif days_elapsed < 14:
            current_phase = "phase_2"
        elif days_elapsed < 28:
            current_phase = "phase_3"
        else:
            current_phase = "phase_4"
        
        return (current_phase, start_date)
    
    def load_shadow_learning_insights(self) -> Dict[str, Any]:
        """تحميل رؤى Shadow Learning من البيانات"""
        insights_file = self.data_dir / "learning_insights.json"
        
        if not insights_file.exists():
            self.logger.warning(f"Shadow Learning insights not found: {insights_file}")
            return {}
        
        with open(insights_file, 'r', encoding='utf-8') as f:
            return json.load(f)
    
    def generate_quality_adjustment_config(self, phase_name: str) -> Dict[str, Any]:
        """توليد إعدادات جودة الإشارة بناءً على المرحلة"""
        phase = GRADUAL_ROLLOUT_CONFIG.get(phase_name, {})
        
        config = {
            "phase_name": phase.get("name"),
            "timestamp": datetime.now().isoformat(),
            "quality_adjustments": {}
        }
        
        if phase_name == "phase_1":
            config["quality_adjustments"] = {
                "QUALITY_SCORE_TRUST_ENABLED": False,  # لم يتم التفعيل بعد
                "apply_rate": 0.0,
                "notes": "Monitoring phase - no changes yet"
            }
        
        elif phase_name == "phase_2":
            config["quality_adjustments"] = {
                "QUALITY_SCORE_TRUST_ENABLED": True,
                "apply_rate": phase.get("apply_rate", 0.3),
                "quality_threshold_adjustment": 0,
                "notes": "Soft enablement with 30% apply rate"
            }
        
        elif phase_name == "phase_3":
            schedule = phase.get("quality_threshold_reduction_schedule", [])
            current_reduction = next(
                (s["cumulative"] for s in schedule if s["day"] <= 7),
                -10
            )
            config["quality_adjustments"] = {
                "QUALITY_SCORE_TRUST_ENABLED": True,
                "apply_rate": phase.get("apply_rate", 1.0),
                "quality_threshold_adjustment": current_reduction,
                "quality_threshold_reduction_per_phase": -2,
                "notes": f"Progressive reduction - current: {current_reduction} points"
            }
        
        elif phase_name == "phase_4":
            config["quality_adjustments"] = {
                "QUALITY_SCORE_TRUST_ENABLED": True,
                "apply_rate": 1.0,
                "high_quality_confidence_floor": phase.get("high_quality_confidence_floor"),
                "high_quality_risk_multiplier": phase.get("high_quality_risk_multiplier"),
                "newyork_quality_floor_adjustment": phase.get("newyork_quality_floor_adjustment"),
                "notes": "Tightening high-quality standards"
            }
        
        return config
    
    def apply_recommendations(self) -> Dict[str, Any]:
        """تطبيق التوصيات للمرحلة الحالية"""
        phase_name, phase_start = self.get_current_phase()
        phase_config = GRADUAL_ROLLOUT_CONFIG[phase_name]
        
        self.logger.info(f"🌑 APPLYING SHADOW LEARNING RECOMMENDATIONS")
        self.logger.info(f"   Current Phase: {phase_config['name']}")
        self.logger.info(f"   Started: {phase_start.strftime('%Y-%m-%d %H:%M:%S')}")
        
        # تحميل رؤى Shadow Learning
        insights = self.load_shadow_learning_insights()
        
        # توليد إعدادات الجودة
        quality_config = self.generate_quality_adjustment_config(phase_name)
        
        # حفظ الإعدادات
        config_file = self.config_dir / "shadow_learning_adjustments.json"
        config_file.parent.mkdir(parents=True, exist_ok=True)
        with open(config_file, 'w', encoding='utf-8') as f:
            json.dump(quality_config, f, indent=2, ensure_ascii=False)
        
        result = {
            "status": "success",
            "phase": phase_name,
            "phase_name": phase_config["name"],
            "days_elapsed": (datetime.now() - phase_start).days,
            "actions": phase_config.get("actions", []),
            "quality_adjustments": quality_config["quality_adjustments"],
            "shadow_learning_stats": insights.get("observed_statistics", {}),
            "timestamp": datetime.now().isoformat()
        }
        
        # طباعة النتائج
        self._print_application_report(result)
        
        return result
    
    def _print_application_report(self, result: Dict[str, Any]):
        """طباعة تقرير التطبيق"""
        print("\n" + "="*80)
        print("🌑 SHADOW LEARNING RECOMMENDATIONS APPLICATION REPORT")
        print("="*80)
        
        print(f"\n📊 Current Phase: {result['phase_name']} (Day {result['days_elapsed']})")
        
        print(f"\n📋 Recommended Actions:")
        for action in result.get("actions", []):
            print(f"   • {action}")
        
        print(f"\n⚙️  Quality Adjustments:")
        for key, value in result.get("quality_adjustments", {}).items():
            print(f"   • {key}: {value}")
        
        if result.get("shadow_learning_stats"):
            stats = result["shadow_learning_stats"]
            print(f"\n📈 Shadow Learning Statistics:")
            print(f"   • Signals Analyzed: {stats.get('total_signals', 'N/A')}")
            print(f"   • Observed Win Rate: {stats.get('win_rate', 'N/A')}")
            print(
                "   • Average Outcome Price Distance: "
                f"{stats.get('average_outcome_price_distance', 'N/A')}"
            )
            print(f"   • Average R:R: {stats.get('avg_rr_ratio', 'N/A')}")
        
        print("\n✅ Configuration saved to config/shadow_learning_adjustments.json")
        print("="*80 + "\n")
    
    def get_gradual_rollout_schedule(self) -> str:
        """الحصول على جدول الدورة التدريجية الكاملة"""
        schedule_lines = ["🌑 SHADOW LEARNING GRADUAL ROLLOUT SCHEDULE\n"]
        schedule_lines.append("="*80)
        
        for phase_num, (phase_key, phase_data) in enumerate(GRADUAL_ROLLOUT_CONFIG.items(), 1):
            schedule_lines.append(f"\n{phase_num}️⃣  {phase_data['name']}")
            schedule_lines.append(f"   Duration: {phase_data['duration_days']} days")
            schedule_lines.append(f"   Status: {phase_data['status']}")
            schedule_lines.append(f"   Actions:")
            for action in phase_data.get("actions", []):
                schedule_lines.append(f"      • {action}")
            
            if "quality_threshold_reduction_schedule" in phase_data:
                schedule_lines.append(f"   Reduction Schedule:")
                for entry in phase_data["quality_threshold_reduction_schedule"]:
                    schedule_lines.append(
                        f"      • Day {entry['day']}: {entry['reduction']:+d} "
                        f"(Cumulative: {entry['cumulative']:+d})"
                    )
        
        schedule_lines.append("\n" + "="*80)
        return "\n".join(schedule_lines)


if __name__ == "__main__":
    applier = ShadowLearningRecommendationsApplier(".")
    
    # طباعة الجدول الكامل
    print(applier.get_gradual_rollout_schedule())
    
    # تطبيق التوصيات
    result = applier.apply_recommendations()
    
    print("\n✅ Shadow Learning Recommendations Applied Successfully!")
    print(f"   Configuration saved to: config/shadow_learning_adjustments.json")
