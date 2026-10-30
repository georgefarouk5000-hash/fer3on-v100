#!/usr/bin/env python3
"""
📊 FER3ON Performance Monitoring Dashboard
لوحة تحكم لمراقبة الأداء والتحسينات في الوقت الفعلي

الميزات:
  1. عرض إحصائيات الأداء الحالية من Truth Layer
  2. مراقبة توصيات Shadow Learning
  3. تتبع أحدث نتائج التطور الجيني المتاحة
  4. عدم اختلاق خط أساس أو حدود تنبيه غير معتمدة
"""

import json
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any, Optional


class PerformanceMonitoringDashboard:
    """لوحة تحكم مراقبة الأداء والتحسينات"""

    def __init__(self, project_root: str = "."):
        self.project_root = Path(project_root)
        self.data_dir = self.project_root / "data" / "analytics"
        self.config_dir = self.project_root / "config"

    def load_current_performance(self) -> Dict[str, Any]:
        """Read current-build closed-trade metrics from the Truth Layer."""
        from analytics.performance_repository import get_all_trades, safe_metrics_dict
        from analytics.truth_layer import compute_metrics
        from core.settings import BUILD_ID

        trades = [trade for trade in get_all_trades() if trade.close_time]
        if not trades:
            return {
                "status": "no_data",
                "source": "truth_layer",
                "build_id": BUILD_ID,
                "closed_trades": 0,
                "metrics": None,
            }
        return {
            "status": "available",
            "source": "truth_layer",
            "build_id": BUILD_ID,
            "closed_trades": len(trades),
            "metrics": safe_metrics_dict(compute_metrics(trades)),
        }
    
    def load_shadow_learning_data(self) -> Dict[str, Any]:
        """تحميل بيانات Shadow Learning"""
        insights_file = self.data_dir / "shadow_learning" / "learning_insights.json"
        
        if not insights_file.exists():
            return {"status": "not_found"}
        
        with open(insights_file, 'r', encoding='utf-8') as f:
            insights = json.load(f)
        
        stats = insights.get("observed_statistics", {})
        recommendations = insights.get("recommendations", [])
        
        return {
            "status": insights.get("status", "legacy_unverified"),
            "date": insights.get("generated_at", "N/A"),
            "signals_analyzed": insights.get("sample_count", 0),
            "observed_win_rate": stats.get("win_rate"),
            "avg_outcome_price_distance": stats.get("average_outcome_price_distance"),
            "avg_rr": stats.get("avg_rr_ratio"),
            "ready_for_recommendations": insights.get("ready_for_recommendations", False),
            "high_priority_recommendations": [
                r for r in recommendations
                if insights.get("ready_for_recommendations") and r.get("priority") == "HIGH"
            ],
            "medium_priority_recommendations": [
                r for r in recommendations
                if insights.get("ready_for_recommendations") and r.get("priority") == "MEDIUM"
            ],
        }
    
    def load_genetic_evolution_results(self) -> Dict[str, Any]:
        """تحميل نتائج التطور الجيني"""
        evolution_dir = self.data_dir / "evolution"
        
        if not evolution_dir.exists():
            return {"status": "not_found"}
        
        # البحث عن أحدث ملف نتائج
        result_files = sorted(evolution_dir.glob("genetic_evolution_results_*.json"))
        
        if not result_files:
            return {"status": "no_results"}
        
        latest_file = result_files[-1]
        
        with open(latest_file, 'r', encoding='utf-8') as f:
            results = json.load(f)
        
        best = results.get("final_best_parameters", {})
        improvement = results.get("improvement_over_baseline", {})
        
        return {
            "status": "loaded",
            "file": latest_file.name,
            "generations": results.get("generations_completed", 0),
            "best_fitness": best.get("fitness_score", 0),
            "best_parameters": {
                "risk_percent": best.get("risk_percent", "N/A"),
                "max_trades_per_day": best.get("max_trades_per_day", "N/A"),
                "tp_multiplier": best.get("tp_multiplier", "N/A"),
                "sl_multiplier": best.get("sl_multiplier", "N/A"),
                "confidence_threshold": best.get("confidence_threshold", "N/A"),
                "quality_floor": best.get("quality_floor", "N/A"),
            },
            "improvement": {
                "fitness": improvement.get("fitness_improvement", 0),
                "win_rate": improvement.get("win_rate_change", 0),
                "profit_factor": improvement.get("profit_factor_change", 0),
            }
        }
    
    def load_quality_adjustments(self) -> Dict[str, Any]:
        """تحميل تعديلات جودة الإشارة الحالية"""
        config_file = self.config_dir / "shadow_learning_adjustments.json"
        
        if not config_file.exists():
            return {"status": "not_found"}
        
        with open(config_file, 'r', encoding='utf-8') as f:
            config = json.load(f)
        
        return {
            "status": "loaded",
            "phase": config.get("phase_name", "Unknown"),
            "timestamp": config.get("timestamp", "N/A"),
            "adjustments": config.get("quality_adjustments", {})
        }
    
    def check_performance_alerts(self, current_metrics: Optional[Dict] = None) -> List[Dict]:
        """No alerts are emitted until performance thresholds are explicitly configured."""
        return []
    
    def generate_performance_report(self) -> str:
        """توليد تقرير الأداء الشامل"""
        report_lines = ["\n" + "="*80]
        report_lines.append("📊 FER3ON PERFORMANCE MONITORING DASHBOARD")
        report_lines.append("="*80 + "\n")
        
        # 1. Current-build performance
        performance = self.load_current_performance()
        report_lines.append("📈 CURRENT-BUILD CLOSED-TRADE PERFORMANCE")
        report_lines.append("-" * 80)
        if performance["status"] == "available":
            metrics = performance["metrics"]
            report_lines.append(f"  Source:             Truth Layer / build {performance['build_id']}")
            report_lines.append(f"  Closed Trades:      {performance['closed_trades']}")
            report_lines.append(f"  Win Rate:           {metrics['win_rate']:.1%}")
            pf = metrics["profit_factor"]
            report_lines.append(f"  Profit Factor:      {'∞' if pf is None else f'{pf:.2f}'}")
            report_lines.append(f"  Net P&L:            ${metrics['net_pnl']:,.2f}")
            report_lines.append(f"  Expectancy:         ${metrics['expectancy']:,.2f}")
            report_lines.append(f"  Max Drawdown:       ${metrics['max_drawdown']:,.2f}\n")
        else:
            report_lines.append(
                f"  Status:             NO CLOSED TRADES for build {performance['build_id']}\n"
            )
        
        # 2. Shadow Learning
        report_lines.append("🌑 SHADOW LEARNING ANALYSIS")
        report_lines.append("-" * 80)
        shadow_data = self.load_shadow_learning_data()
        
        if shadow_data.get("status") == "success":
            report_lines.append(
                "  Status:             "
                + ("✅ READY" if shadow_data["ready_for_recommendations"] else "⏳ COLLECTING")
            )
            report_lines.append(f"  Signals Analyzed:   {shadow_data['signals_analyzed']:,}")
            report_lines.append(f"  Observed Win Rate:  {shadow_data['observed_win_rate']:.2%}")
            report_lines.append(
                "  Avg Price Distance:"
                f" {shadow_data['avg_outcome_price_distance']:.2f}"
            )
            report_lines.append(f"  Avg R:R:            {shadow_data['avg_rr']:.2f}")
            
            report_lines.append(f"\n  🔴 HIGH PRIORITY RECOMMENDATIONS:")
            for rec in shadow_data.get("high_priority_recommendations", []):
                report_lines.append(f"     • {rec.get('description', 'N/A')}")
            
            report_lines.append(f"\n  🟡 MEDIUM PRIORITY RECOMMENDATIONS:")
            for rec in shadow_data.get("medium_priority_recommendations", []):
                report_lines.append(f"     • {rec.get('description', 'N/A')}")
        elif shadow_data.get("status") == "insufficient_data":
            report_lines.append("  Status:             ⏳ WAITING FOR CANDLE-RESOLVED DATA\n")
        else:
            report_lines.append(f"  Status:             ⏳ NOT YET GENERATED\n")
        
        # 3. جودة الإشارات
        report_lines.append("\n⚙️  QUALITY SCORE ADJUSTMENTS")
        report_lines.append("-" * 80)
        quality_data = self.load_quality_adjustments()
        
        if quality_data.get("status") == "loaded":
            report_lines.append(f"  Current Phase:      {quality_data['phase']}")
            for key, value in quality_data.get("adjustments", {}).items():
                report_lines.append(f"  {key.replace('_', ' ').title()}: {value}")
        else:
            report_lines.append(f"  Status:             ⏳ MONITORING PHASE (No changes yet)\n")
        
        # 4. التطور الجيني
        report_lines.append("\n🧬 GENETIC PARAMETER EVOLUTION")
        report_lines.append("-" * 80)
        evolution_data = self.load_genetic_evolution_results()
        
        if evolution_data.get("status") == "loaded":
            report_lines.append(f"  Status:             ✅ COMPLETED")
            report_lines.append(f"  Generations:        {evolution_data['generations']}")
            report_lines.append(f"  Best Fitness:       {evolution_data['best_fitness']:.2f}")
            
            report_lines.append(f"\n  🏆 Optimized Parameters:")
            for param, value in evolution_data.get("best_parameters", {}).items():
                report_lines.append(f"     {param.replace('_', ' ').title()}: {value}")
            
            report_lines.append(f"\n  📈 Improvement over Baseline:")
            impr = evolution_data.get("improvement", {})
            report_lines.append(f"     Fitness:        {impr.get('fitness', 0):+.2%}")
            report_lines.append(f"     Win Rate:       {impr.get('win_rate', 0):+.2%}")
            report_lines.append(f"     Profit Factor:  {impr.get('profit_factor', 0):+.2f}")
        else:
            report_lines.append(f"  Status:             ⏳ PENDING EXECUTION\n")
        
        # 5. التنبيهات
        report_lines.append("\n🚨 PERFORMANCE ALERTS")
        report_lines.append("-" * 80)
        alerts = self.check_performance_alerts()
        
        if alerts:
            for alert in alerts:
                severity_emoji = "🔴" if alert["severity"] == "HIGH" else "🟡"
                report_lines.append(f"  {severity_emoji} [{alert['severity']}] {alert['type']}")
                report_lines.append(f"     Message: {alert['message']}")
                report_lines.append(f"     Action:  {alert['recommendation']}\n")
        else:
            report_lines.append(
                "  Not evaluated: no validated performance alert thresholds are configured.\n"
            )
        
        # 6. التوصيات والخطوات التالية
        report_lines.append("📋 RECOMMENDED NEXT STEPS")
        report_lines.append("-" * 80)
        report_lines.append("  SHORT TERM (This Week):")
        report_lines.append("    1. Monitor Shadow Learning insights daily")
        report_lines.append("    2. Verify no degradation in trade execution")
        report_lines.append("    3. Collect 50+ new trades for recalibration")
        report_lines.append("\n  MEDIUM TERM (This Month):")
        report_lines.append("    1. Apply quality score adjustments gradually")
        report_lines.append("    2. Test optimized parameters from genetic evolution")
        report_lines.append("    3. Review current-build Truth Layer metrics")
        report_lines.append("\n  LONG TERM (This Quarter):")
        report_lines.append("    1. Implement ML model training on shadow data")
        report_lines.append("    2. Run full backtest with optimized parameters")
        report_lines.append("    3. Prepare for next evolution cycle")
        
        report_lines.append("\n" + "="*80)
        report_lines.append(f"📅 Report Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        report_lines.append("="*80 + "\n")
        
        return "\n".join(report_lines)
    
    def save_dashboard_snapshot(self) -> Path:
        """حفظ لقطة من لوحة التحكم الحالية"""
        snapshot = {
            "timestamp": datetime.now().isoformat(),
            "current_performance": self.load_current_performance(),
            "shadow_learning": self.load_shadow_learning_data(),
            "quality_adjustments": self.load_quality_adjustments(),
            "genetic_evolution": self.load_genetic_evolution_results(),
            "performance_alerts": self.check_performance_alerts(),
        }
        
        snapshot_dir = self.project_root / "data" / "dashboards"
        snapshot_dir.mkdir(parents=True, exist_ok=True)
        
        filename = f"dashboard_snapshot_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        filepath = snapshot_dir / filename
        
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(snapshot, f, indent=2, ensure_ascii=False)
        
        return filepath
    
    def create_html_dashboard(self) -> Path:
        """إنشاء لوحة تحكم HTML تفاعلية"""
        performance = self.load_current_performance()
        if performance["status"] == "available":
            metrics = performance["metrics"]
            pf = metrics["profit_factor"]
            performance_values = (
                f'<div class="metric"><span class="metric-label">Closed Trades</span>'
                f'<span class="metric-value">{performance["closed_trades"]}</span></div>'
                f'<div class="metric"><span class="metric-label">Win Rate</span>'
                f'<span class="metric-value">{metrics["win_rate"]:.2%}</span></div>'
                f'<div class="metric"><span class="metric-label">Profit Factor</span>'
                f'<span class="metric-value">{"∞" if pf is None else f"{pf:.2f}"}</span></div>'
                f'<div class="metric"><span class="metric-label">Net P&amp;L</span>'
                f'<span class="metric-value">${metrics["net_pnl"]:,.2f}</span></div>'
                f'<div class="metric"><span class="metric-label">Build</span>'
                f'<span class="metric-value">{performance["build_id"]}</span></div>'
            )
        else:
            performance_values = (
                f'<div class="metric"><span class="metric-label">Status</span>'
                f'<span class="metric-value status-pending">NO CLOSED TRADES</span></div>'
                f'<div class="metric"><span class="metric-label">Build</span>'
                f'<span class="metric-value">{performance["build_id"]}</span></div>'
            )
        performance_card_html = (
            '<div class="card"><h2>Current-Build Performance</h2>'
            '<div class="metric"><span class="metric-label">Source</span>'
            '<span class="metric-value">Truth Layer</span></div>'
            f'{performance_values}</div>'
        )

        evolution_data = self.load_genetic_evolution_results()
        evolution_status = (
            f"COMPLETED · {evolution_data['generations']} generations"
            if evolution_data.get("status") == "loaded"
            else "NO RESULTS"
        )
        fitness = (
            f"{evolution_data['best_fitness']:.2f}"
            if evolution_data.get("status") == "loaded"
            else "N/A"
        )
        evolution_card_html = f"""
            <div class="card">
                <h2>Genetic Evolution</h2>
                <div class="metric">
                    <span class="metric-label">Status</span>
                    <span class="metric-value">{evolution_status}</span>
                </div>
                <div class="metric">
                    <span class="metric-label">Best Recorded Fitness</span>
                    <span class="metric-value">{fitness}</span>
                </div>
            </div>
            """

        quality_data = self.load_quality_adjustments()
        quality_status = (
            f"LOADED · {quality_data['phase']}"
            if quality_data.get("status") == "loaded"
            else "NO ADJUSTMENT FILE"
        )
        quality_card_html = f"""
            <div class="card">
                <h2>Quality Adjustments</h2>
                <div class="metric">
                    <span class="metric-label">Status</span>
                    <span class="metric-value">{quality_status}</span>
                </div>
                <div class="metric">
                    <span class="metric-label">Recorded Adjustments</span>
                    <span class="metric-value">{len(quality_data.get("adjustments", {}))}</span>
                </div>
            </div>
            """

        shadow_data = self.load_shadow_learning_data()
        shadow_status = shadow_data.get("status")
        if shadow_status == "success":
            shadow_ready = bool(shadow_data.get("ready_for_recommendations"))
            shadow_status_text = "READY" if shadow_ready else "COLLECTING"
            observed_rate = shadow_data.get("observed_win_rate")
            observed_rate_text = (
                f"{observed_rate:.2%}" if observed_rate is not None else "N/A"
            )
            average_distance = shadow_data.get("avg_outcome_price_distance")
            average_distance_text = (
                f"{average_distance:.2f}" if average_distance is not None else "N/A"
            )
            average_rr = shadow_data.get("avg_rr")
            average_rr_text = f"{average_rr:.2f}" if average_rr is not None else "N/A"
            shadow_card_html = f"""
            <div class="card">
                <h2>Shadow Learning</h2>
                <div class="metric">
                    <span class="metric-label">Status</span>
                    <span class="metric-value {'status-active' if shadow_ready else 'status-pending'}">{shadow_status_text}</span>
                </div>
                <div class="metric">
                    <span class="metric-label">Candle-Resolved Signals</span>
                    <span class="metric-value">{shadow_data['signals_analyzed']:,}</span>
                </div>
                <div class="metric">
                    <span class="metric-label">Observed Win Rate</span>
                    <span class="metric-value">{observed_rate_text}</span>
                </div>
                <div class="metric">
                    <span class="metric-label">Avg Price Distance / R:R</span>
                    <span class="metric-value">{average_distance_text} / {average_rr_text}</span>
                </div>
            </div>
            """
        else:
            status_text = (
                "WAITING FOR CANDLE-RESOLVED DATA"
                if shadow_status == "insufficient_data"
                else "LEGACY DATA NOT VERIFIED"
                if shadow_status == "legacy_unverified"
                else "NOT YET GENERATED"
            )
            shadow_card_html = f"""
            <div class="card">
                <h2>Shadow Learning</h2>
                <div class="metric">
                    <span class="metric-label">Status</span>
                    <span class="metric-value status-pending">{status_text}</span>
                </div>
                <div class="metric">
                    <span class="metric-label">Observed Metrics</span>
                    <span class="metric-value">Unavailable</span>
                </div>
            </div>
            """

        html_content = """<!DOCTYPE html>
<html dir="rtl" lang="ar">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>FER3ON Performance Dashboard</title>
    <style>
        * { margin: 0; padding: 0; }
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: #0f1419;
            color: #e0e0e0;
            padding: 20px;
        }
        .header {
            text-align: center;
            margin-bottom: 30px;
            border-bottom: 3px solid #ffd700;
            padding-bottom: 20px;
        }
        .header h1 {
            font-size: 2.5em;
            color: #ffd700;
        }
        .container {
            max-width: 1400px;
            margin: 0 auto;
        }
        .grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(350px, 1fr));
            gap: 20px;
            margin-bottom: 30px;
        }
        .card {
            background: #1a1f2a;
            border: 2px solid #ffd700;
            border-radius: 8px;
            padding: 20px;
            box-shadow: 0 0 20px rgba(255, 215, 0, 0.1);
        }
        .card h2 {
            color: #ffd700;
            margin-bottom: 15px;
            font-size: 1.3em;
            border-bottom: 2px solid #ffd700;
            padding-bottom: 10px;
        }
        .metric {
            display: flex;
            justify-content: space-between;
            padding: 10px 0;
            border-bottom: 1px solid #333;
        }
        .metric:last-child {
            border-bottom: none;
        }
        .metric-label {
            font-weight: bold;
            color: #b0b0b0;
        }
        .metric-value {
            color: #ffd700;
            font-weight: bold;
        }
        .positive { color: #4ade80; }
        .negative { color: #f87171; }
        .status-active { color: #4ade80; }
        .status-pending { color: #facc15; }
        .alert {
            padding: 12px;
            margin: 10px 0;
            border-left: 4px solid;
            background: rgba(255, 0, 0, 0.1);
        }
        .alert-high { border-left-color: #f87171; }
        .alert-medium { border-left-color: #facc15; }
        .progress-bar {
            width: 100%;
            height: 20px;
            background: #333;
            border-radius: 10px;
            overflow: hidden;
            margin: 10px 0;
        }
        .progress {
            height: 100%;
            background: linear-gradient(90deg, #ffd700, #ffed4e);
            width: 0%;
        }
        .footer {
            text-align: center;
            margin-top: 40px;
            padding-top: 20px;
            border-top: 2px solid #ffd700;
            color: #888;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>FER3ON V5.7 PERFORMANCE DASHBOARD</h1>
            <p>Real-time monitoring of trading system improvements</p>
        </div>
        
        <div class="grid">
            __CURRENT_PERFORMANCE_CARD__
            
            __SHADOW_LEARNING_CARD__
            
            __GENETIC_EVOLUTION_CARD__
            
            __QUALITY_ADJUSTMENTS_CARD__
        </div>
        
        <div class="card" style="grid-column: 1 / -1;">
            <h2>Recommended Next Steps</h2>
            <div style="padding: 15px;">
                <h3 style="color: #ffd700; margin: 10px 0;">Short Term (This Week):</h3>
                <ul style="margin-left: 20px; line-height: 1.8;">
                    <li>Monitor Shadow Learning insights daily</li>
                    <li>Verify no degradation in trade execution</li>
                    <li>Collect 50+ new trades for recalibration</li>
                </ul>
                
                <h3 style="color: #ffd700; margin: 20px 0 10px 0;">Medium Term (This Month):</h3>
                <ul style="margin-left: 20px; line-height: 1.8;">
                    <li>Apply quality score adjustments gradually</li>
                    <li>Test optimized parameters from genetic evolution</li>
                    <li>Review current-build Truth Layer metrics</li>
                </ul>
                
                <h3 style="color: #ffd700; margin: 20px 0 10px 0;">Long Term (This Quarter):</h3>
                <ul style="margin-left: 20px; line-height: 1.8;">
                    <li>Implement ML model training on shadow data</li>
                    <li>Run full backtest with optimized parameters</li>
                    <li>Prepare for next evolution cycle</li>
                </ul>
            </div>
        </div>
        
        <div class="footer">
            <p>FER3ON V5.7 - AI Trading System</p>
            <p>Last Updated: """ + datetime.now().strftime("%Y-%m-%d %H:%M:%S") + """</p>
        </div>
    </div>
</body>
</html>
"""
        html_content = html_content.replace(
            "__SHADOW_LEARNING_CARD__",
            shadow_card_html,
        )
        html_content = html_content.replace(
            "__CURRENT_PERFORMANCE_CARD__",
            performance_card_html,
        )
        html_content = html_content.replace(
            "__GENETIC_EVOLUTION_CARD__",
            evolution_card_html,
        )
        html_content = html_content.replace(
            "__QUALITY_ADJUSTMENTS_CARD__",
            quality_card_html,
        )
        
        dashboard_dir = self.project_root / "dashboards"
        dashboard_dir.mkdir(parents=True, exist_ok=True)
        
        filepath = dashboard_dir / "performance_dashboard.html"
        
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(html_content)
        
        return filepath


if __name__ == "__main__":
    dashboard = PerformanceMonitoringDashboard(".")
    
    # طباعة التقرير النصي
    report = dashboard.generate_performance_report()
    print(report)
    
    # حفظ لقطة
    snapshot_file = dashboard.save_dashboard_snapshot()
    print(f"✅ Dashboard snapshot saved: {snapshot_file}")
    
    # إنشاء لوحة HTML
    html_file = dashboard.create_html_dashboard()
    print(f"✅ HTML Dashboard created: {html_file}")
    print(f"   Open in browser: {html_file.as_posix()}")
