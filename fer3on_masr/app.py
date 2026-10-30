from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from fer3on_masr.api.contracts import default_api_descriptor
from fer3on_masr.director.executive import ExecutiveDirector
from fer3on_masr.explainability.service import ExplainabilityService
from fer3on_masr.integration.adapters import LegacyBridge
from fer3on_masr.intelligence.candles import CandleIntelligence
from fer3on_masr.intelligence.liquidity import LiquidityIntelligence
from fer3on_masr.intelligence.market import MarketIntelligenceLayer
from fer3on_masr.intelligence.orderflow import OrderFlowIntelligence
from fer3on_masr.intelligence.range_forecast import RangeIntelligence
from fer3on_masr.intelligence.timeframes import TimeframeIntelligence
from fer3on_masr.intelligence.volume_profile import VolumeProfileIntelligence
from fer3on_masr.intelligence.vwap import AnchoredVWAPIntelligence
from fer3on_masr.kernel.context import build_context
from fer3on_masr.learning.center import LearningCenter
from fer3on_masr.learning.evolution import AdaptiveWeightOptimizer, EvolutionEngine, PatternDiscovery
from fer3on_masr.learning.history_loader import (
    build_diagnostic_records,
    build_discovery_batch,
    compute_history_stats,
    to_evolution_record,
)
from fer3on_masr.learning.knowledge_graph import KnowledgeGraph
from fer3on_masr.optimization.performance import PerformanceOptimizer
from fer3on_masr.strategy_ai.agents import StrategyAgentFactory


class Fer3onMasrApp:
    def __init__(self, root_path: str | Path) -> None:
        self.root = Path(root_path).resolve()
        self.context = build_context(self.root.as_posix())
        self.market = MarketIntelligenceLayer()
        self.timeframes = TimeframeIntelligence()
        self.candles = CandleIntelligence()
        self.liquidity = LiquidityIntelligence()
        self.orderflow = OrderFlowIntelligence()
        self.volume_profile = VolumeProfileIntelligence()
        self.vwap = AnchoredVWAPIntelligence()
        self.ranges = RangeIntelligence()
        self.bridge = LegacyBridge()
        self.director = ExecutiveDirector()
        self.explainability = ExplainabilityService()
        self.weights = AdaptiveWeightOptimizer(window=500)
        self.evolution = EvolutionEngine()
        self.discovery = PatternDiscovery()
        self.performance = PerformanceOptimizer()
        self.learning_center = LearningCenter(self.context.config.learning_center_path)
        self.knowledge_graph = KnowledgeGraph(self.context.config.knowledge_graph_path)
        self.knowledge_graph.seed_default_relations()
        self.knowledge_graph.save()
        self.agents = StrategyAgentFactory.build_default_agents()

    def run_cycle(self, rates: list[dict[str, Any]], symbol: str | None = None) -> dict[str, Any]:
        symbol = symbol or self.context.config.symbol
        step = self.performance.start("build_snapshot")
        snapshot = self.bridge.build_snapshot(rates, symbol=symbol)
        step.stop()

        step = self.performance.start("market_intelligence")
        market_reports = self.market.analyze(snapshot)
        step.stop()

        step = self.performance.start("timeframe_intelligence")
        timeframe_reports = self.timeframes.analyze(rates, self.context.config.timeframes)
        step.stop()

        candle_predictions = self.candles.predict(rates)

        # === Liquidity Analyst now receives snapshot (sweep_probability/direction) ===
        liquidity_profile = self.liquidity.profile(rates, snapshot=snapshot)

        # === Order Flow Analyst (synthetic — transparent about that) ===
        step = self.performance.start("orderflow_intelligence")
        orderflow_report = self.orderflow.analyze(rates, snapshot=snapshot)
        step.stop()

        # === Volume Profile Analyst (real POC/VAH/VAL/HVN/LVN) ===
        step = self.performance.start("volume_profile_intelligence")
        volume_profile_report = self.volume_profile.analyze(rates)
        step.stop()

        # === Anchored VWAP Analyst (real VWAP with volume weighting) ===
        step = self.performance.start("anchored_vwap_intelligence")
        vwap_report = self.vwap.analyze(rates, anchor="session_open")
        step.stop()

        range_forecast = self.ranges.forecast(rates, snapshot.get("atr", 0.0))

        # ---- real historical data (replaces the old hardcoded example dict) ----
        step = self.performance.start("history_intelligence")
        history_stats = compute_history_stats(limit=100)
        diagnostic_records = build_diagnostic_records(limit=200)
        step.stop()

        market_bias = next((r.bias for r in market_reports if r.name == "Trend Engine"), "BUY")
        base_confidence = next((r.confidence for r in market_reports if r.name == "Trend Engine"), 60.0)
        structure_report = next((r for r in market_reports if r.name == "Structure Engine"), None)
        news_report = next((r for r in market_reports if r.name == "News Engine"), None)

        # ---- rich, agent-differentiated context ----
        context = {
            "market_bias": market_bias,
            "base_confidence": base_confidence,
            "risk_cap": min(self.context.config.max_risk_pct, 0.42),
            "lot_cap": min(self.context.config.max_lot, 0.18),
            "timeframes": {report.timeframe: report.to_dict() for report in timeframe_reports},
            "liquidity": liquidity_profile.to_dict(),
            "candles": [item.to_dict() for item in candle_predictions],
            "structure_bias": structure_report.bias if structure_report else market_bias,
            "structure_confidence": structure_report.confidence if structure_report else base_confidence,
            "news_bias": news_report.bias if news_report else "NEUTRAL",
            "session": snapshot.get("session", "UNKNOWN"),
            "market_regime": snapshot.get("market_regime", "UNKNOWN"),
            "history_stats": history_stats,
            # === NEW: sweep + orderflow + vwap + volume profile exposed to agents ===
            "sweep_probability": snapshot.get("sweep_probability", 0.0),
            "sweep_direction": snapshot.get("sweep_direction", "NONE"),
            "sweep_confidence_bonus": snapshot.get("sweep_confidence_bonus", 0.0),
            "orderflow": orderflow_report.to_dict(),
            "volume_profile": volume_profile_report.to_dict(),
            "anchored_vwap": vwap_report.to_dict(),
        }

        strategy_decisions = []
        for agent in self.agents:
            weight = self.weights.update(agent.name, base_confidence / 100.0)
            strategy_decisions.append(agent.evaluate(context, weight=weight))

        plan = self.director.decide(strategy_decisions)
        explain = self.explainability.build(plan, strategy_decisions)

        if diagnostic_records:
            evolution_inputs = [to_evolution_record(r) for r in diagnostic_records]
            diagnosis = self.evolution.diagnose_recent(evolution_inputs)
            diagnosis["data_source"] = "real_trade_history_csv"

            discovery_inputs = build_discovery_batch(diagnostic_records)
            discovered = self.discovery.discover(discovery_inputs)
        else:
            diagnosis = {
                "sample_size": 0,
                "reason_counts": {},
                "reason_counts_on_losses": {},
                "most_common_reason": None,
                "most_common_loss_reason": None,
                "per_trade_sample": [],
                "data_source": "no_history_available",
            }
            discovered = []

        if discovered:
            for item in discovered:
                self.knowledge_graph.add_relation(
                    item["pattern"], "registered_as", "Discovered Pattern", item["success"] / 100.0,
                    sample_size=item.get("sample_size"),
                )
            self.knowledge_graph.save()

        self.learning_center.register_artifact(self.context.config.knowledge_graph_path, "knowledge_graph", ["masr", "graph"])
        self.learning_center.register_artifact(self.root / "README_MASR.md", "docs", ["masr", "roadmap"])

        return {
            "config": self.context.config.to_dict(),
            "api": asdict(default_api_descriptor()),
            "market_intelligence": [report.to_dict() for report in market_reports],
            "timeframe_intelligence": [report.to_dict() for report in timeframe_reports],
            "candle_intelligence": [item.to_dict() for item in candle_predictions],
            "liquidity_intelligence": liquidity_profile.to_dict(),
            "orderflow_intelligence": orderflow_report.to_dict(),
            "volume_profile_intelligence": volume_profile_report.to_dict(),
            "anchored_vwap_intelligence": vwap_report.to_dict(),
            "range_intelligence": range_forecast.to_dict(),
            "strategy_ai": [decision.to_dict() for decision in strategy_decisions],
            "executive_director": plan.to_dict(),
            "explainability": explain.to_dict(),
            "adaptive_weights": self.weights.weights(),
            "evolution": diagnosis,
            "pattern_discovery": discovered,
            "history_stats": history_stats,
            "knowledge_graph_query": self.knowledge_graph.query("liquidity"),
            "performance": self.performance.summary(),
        }


def build_sample_rates() -> list[dict[str, Any]]:
    seed = [
        2330.0, 2331.2, 2332.8, 2334.1, 2333.7, 2335.6, 2337.4, 2338.2,
        2336.9, 2339.1, 2340.7, 2342.1, 2341.6, 2343.2, 2344.0, 2345.5,
    ]
    rates = []
    for idx, close in enumerate(seed):
        open_price = seed[idx - 1] if idx else close - 0.7
        high = max(open_price, close) + 0.9
        low = min(open_price, close) - 0.8
        rates.append({
            "open": open_price,
            "high": high,
            "low": low,
            "close": close,
            "tick_volume": 100 + idx * 5,
            "real_volume": 0,
            "time": 1_700_000_000 + idx * 3600,
        })
    return rates


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    app = Fer3onMasrApp(root)
    result = app.run_cycle(build_sample_rates())
    output_path = root / "data" / "fer3on_masr_demo_output.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(output_path.as_posix())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
