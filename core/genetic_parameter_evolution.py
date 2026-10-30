#!/usr/bin/env python3
"""
🧬 Genetic Parameter Evolution Engine
تطوير المعاملات تلقائياً باستخدام خوارزمية تطورية (GA)

الفكرة:
  1. البدء بمجموعة من المعاملات الحالية (الجيدة)
  2. إنشاء أجيال جديدة عبر التطفير (Mutation) والعبور (Crossover)
  3. اختبار كل جيل (Backtest)
  4. الاحتفاظ بالأفضل، التخلص من الأسوأ
  5. تكرار حتى الوصول للتقارب

المعاملات المراد تطويرها:
  - Risk percent per trade (0.3% - 1.0%)
  - Max trades per day (3 - 8)
  - Take Profit multiplier (1.5 - 3.0)
  - Stop Loss multiplier (0.5 - 1.5)
  - Confidence threshold (40% - 75%)
  - Quality floor (40 - 65)
"""

import json
import random
import logging
from pathlib import Path
from typing import Dict, List, Tuple, Any
from dataclasses import dataclass, asdict
from datetime import datetime
import statistics

# =========================================================================
# PARAMETER SPACE DEFINITION
# =========================================================================

@dataclass
class ParameterGene:
    """تمثيل جين (معامل واحد) في الخوارزمية"""
    risk_percent: float           # 0.3 - 1.0
    max_trades_per_day: int       # 3 - 8
    tp_multiplier: float          # 1.5 - 3.0
    sl_multiplier: float          # 0.5 - 1.5
    confidence_threshold: int     # 40 - 75
    quality_floor: int            # 40 - 65
    
    # التغذية الراجعة (الأداء)
    fitness_score: float = 0.0    # WR% * Sharpe * PF
    win_rate: float = 0.0
    profit_factor: float = 0.0
    sharpe_ratio: float = 0.0
    net_profit: float = 0.0
    
    def __str__(self):
        return (
            f"Risk={self.risk_percent:.1f}% | "
            f"MaxTrades={self.max_trades_per_day} | "
            f"TP={self.tp_multiplier:.1f}x | "
            f"SL={self.sl_multiplier:.1f}x | "
            f"Conf={self.confidence_threshold}% | "
            f"QFloor={self.quality_floor} | "
            f"Fitness={self.fitness_score:.2f}"
        )


class ParameterEvolutionEngine:
    """محرك تطوير المعاملات باستخدام خوارزمية تطورية"""
    
    # فضاء المعاملات (الحد الأدنى والأقصى لكل معامل)
    PARAMETER_SPACE = {
        "risk_percent": (0.3, 1.0),
        "max_trades_per_day": (3, 8),
        "tp_multiplier": (1.5, 3.0),
        "sl_multiplier": (0.5, 1.5),
        "confidence_threshold": (40, 75),
        "quality_floor": (40, 65),
    }
    
    # المعاملات الحالية الجيدة (baseline)
    BASELINE_PARAMETERS = {
        "risk_percent": 0.5,
        "max_trades_per_day": 5,
        "tp_multiplier": 2.0,
        "sl_multiplier": 1.0,
        "confidence_threshold": 55,
        "quality_floor": 50,
    }
    
    # معاملات الخوارزمية التطورية
    EVOLUTION_CONFIG = {
        "population_size": 30,        # عدد الأفراد في كل جيل
        "generations": 10,            # عدد الأجيال
        "mutation_rate": 0.15,        # احتمال التطفير
        "crossover_rate": 0.80,       # احتمال العبور
        "elite_ratio": 0.10,          # نسبة النخبة المحفوظة
        "tournament_size": 5,         # حجم البطولة للانتقاء
    }
    
    def __init__(self, project_root: str = "."):
        self.project_root = Path(project_root)
        self.evolution_dir = self.project_root / "data" / "analytics" / "evolution"
        self.evolution_dir.mkdir(parents=True, exist_ok=True)
        
        self._setup_logging()
        self.logger = logging.getLogger("GeneticEvolution")
        
        self.generation = 0
        self.population: List[ParameterGene] = []
        self.evolution_history: List[Dict] = []
    
    def _setup_logging(self):
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s | %(name)s | %(levelname)s | %(message)s'
        )
    
    def create_random_gene(self) -> ParameterGene:
        """إنشاء جين عشوائي"""
        return ParameterGene(
            risk_percent=random.uniform(*self.PARAMETER_SPACE["risk_percent"]),
            max_trades_per_day=random.randint(*self.PARAMETER_SPACE["max_trades_per_day"]),
            tp_multiplier=random.uniform(*self.PARAMETER_SPACE["tp_multiplier"]),
            sl_multiplier=random.uniform(*self.PARAMETER_SPACE["sl_multiplier"]),
            confidence_threshold=random.randint(*self.PARAMETER_SPACE["confidence_threshold"]),
            quality_floor=random.randint(*self.PARAMETER_SPACE["quality_floor"]),
        )
    
    def create_initial_population(self) -> List[ParameterGene]:
        """إنشاء السكان الأوليين (الجيل الأول)"""
        population = []
        
        # إضافة baseline كأفضل حل معروف
        baseline = ParameterGene(
            risk_percent=self.BASELINE_PARAMETERS["risk_percent"],
            max_trades_per_day=self.BASELINE_PARAMETERS["max_trades_per_day"],
            tp_multiplier=self.BASELINE_PARAMETERS["tp_multiplier"],
            sl_multiplier=self.BASELINE_PARAMETERS["sl_multiplier"],
            confidence_threshold=self.BASELINE_PARAMETERS["confidence_threshold"],
            quality_floor=self.BASELINE_PARAMETERS["quality_floor"],
            fitness_score=7.868,  # Sharpe من الـ backtest الحالي
            win_rate=0.64,
            profit_factor=4.105,
            sharpe_ratio=7.868,
            net_profit=172388,
        )
        population.append(baseline)
        
        # إضافة أفراد عشوائيين
        for _ in range(self.EVOLUTION_CONFIG["population_size"] - 1):
            population.append(self.create_random_gene())
        
        return population
    
    def calculate_fitness(self, gene: ParameterGene) -> float:
        """حساب الـ fitness score للجين"""
        # الحالياً: نموذج مبسط (يجب استبداله بـ backtest فعلي)
        # الصيغة: WR% * Sharpe * (PF / 4.1)
        
        if gene.profit_factor <= 0 or gene.sharpe_ratio <= 0:
            return 0.0
        
        fitness = (
            gene.win_rate * 
            gene.sharpe_ratio * 
            (gene.profit_factor / 4.1)
        )
        
        return fitness
    
    def mutate(self, gene: ParameterGene) -> ParameterGene:
        """تطفير الجين (تغيير عشوائي صغير)"""
        mutated = ParameterGene(
            risk_percent=self._mutate_value(
                gene.risk_percent,
                *self.PARAMETER_SPACE["risk_percent"],
                0.2
            ),
            max_trades_per_day=self._mutate_int_value(
                gene.max_trades_per_day,
                *self.PARAMETER_SPACE["max_trades_per_day"],
                1
            ),
            tp_multiplier=self._mutate_value(
                gene.tp_multiplier,
                *self.PARAMETER_SPACE["tp_multiplier"],
                0.3
            ),
            sl_multiplier=self._mutate_value(
                gene.sl_multiplier,
                *self.PARAMETER_SPACE["sl_multiplier"],
                0.15
            ),
            confidence_threshold=self._mutate_int_value(
                gene.confidence_threshold,
                *self.PARAMETER_SPACE["confidence_threshold"],
                3
            ),
            quality_floor=self._mutate_int_value(
                gene.quality_floor,
                *self.PARAMETER_SPACE["quality_floor"],
                3
            ),
        )
        return mutated
    
    def _mutate_value(self, value: float, min_val: float, max_val: float, step: float) -> float:
        """تطفير قيمة عددية"""
        direction = random.choice([-1, 1])
        new_value = value + direction * step * random.random()
        return max(min_val, min(max_val, new_value))
    
    def _mutate_int_value(self, value: int, min_val: int, max_val: int, step: int) -> int:
        """تطفير قيمة صحيحة"""
        direction = random.choice([-1, 1])
        new_value = value + direction * step * random.randint(0, 1)
        return max(min_val, min(max_val, new_value))
    
    def crossover(self, parent1: ParameterGene, parent2: ParameterGene) -> ParameterGene:
        """عبور جينين (دمج المعاملات من الأبوين)"""
        # uniform crossover: خذ كل معامل من أحد الأبوين عشوائياً
        child = ParameterGene(
            risk_percent=parent1.risk_percent if random.random() < 0.5 else parent2.risk_percent,
            max_trades_per_day=parent1.max_trades_per_day if random.random() < 0.5 else parent2.max_trades_per_day,
            tp_multiplier=parent1.tp_multiplier if random.random() < 0.5 else parent2.tp_multiplier,
            sl_multiplier=parent1.sl_multiplier if random.random() < 0.5 else parent2.sl_multiplier,
            confidence_threshold=parent1.confidence_threshold if random.random() < 0.5 else parent2.confidence_threshold,
            quality_floor=parent1.quality_floor if random.random() < 0.5 else parent2.quality_floor,
        )
        
        # قد يحدث تطفير بعد العبور
        if random.random() < self.EVOLUTION_CONFIG["mutation_rate"]:
            child = self.mutate(child)
        
        return child
    
    def select_parents(self, population: List[ParameterGene]) -> Tuple[ParameterGene, ParameterGene]:
        """اختيار أبوين باستخدام tournament selection"""
        tournament_size = self.EVOLUTION_CONFIG["tournament_size"]
        
        # Tournament 1
        tournament1 = random.sample(population, tournament_size)
        parent1 = max(tournament1, key=lambda g: g.fitness_score)
        
        # Tournament 2
        tournament2 = random.sample(population, tournament_size)
        parent2 = max(tournament2, key=lambda g: g.fitness_score)
        
        return parent1, parent2
    
    def evolve_generation(self, population: List[ParameterGene]) -> List[ParameterGene]:
        """تطوير جيل جديد"""
        # ترتيب السكان حسب الـ fitness
        sorted_pop = sorted(population, key=lambda g: g.fitness_score, reverse=True)
        
        # الاحتفاظ بـ elite
        elite_size = max(1, int(len(population) * self.EVOLUTION_CONFIG["elite_ratio"]))
        new_population = sorted_pop[:elite_size]
        
        # إنشاء أفراد جدد عبر التزاوج
        while len(new_population) < len(population):
            if random.random() < self.EVOLUTION_CONFIG["crossover_rate"]:
                parent1, parent2 = self.select_parents(sorted_pop)
                child = self.crossover(parent1, parent2)
            else:
                # نسخ من النخبة مع تطفير
                elite_member = random.choice(sorted_pop[:elite_size])
                child = self.mutate(elite_member)
            
            new_population.append(child)
        
        return new_population[:len(population)]
    
    def run_evolution_simulation(self, generations: int = None) -> Dict[str, Any]:
        """تشغيل محاكاة التطور (بدون backtest فعلي حالياً)"""
        from core.settings import GENETIC_EVOLUTION_LIVE_INFLUENCE
        if GENETIC_EVOLUTION_LIVE_INFLUENCE:
            return {
                "status": "BLOCKED_LIVE_INFLUENCE",
                "reason": "genetic results require out-of-sample validation and promotion",
            }
        if generations is None:
            generations = self.EVOLUTION_CONFIG["generations"]
        
        self.logger.info("🧬 STARTING GENETIC PARAMETER EVOLUTION")
        self.logger.info(f"   Population size: {self.EVOLUTION_CONFIG['population_size']}")
        self.logger.info(f"   Generations: {generations}")
        
        # الجيل الأول
        self.population = self.create_initial_population()
        
        # محاكاة الـ fitness (يجب استبدالها بـ backtest فعلي لاحقاً)
        self._simulate_fitness_scores()
        
        for gen in range(generations):
            self.logger.info(f"\n🧬 Generation {gen + 1}/{generations}")
            
            # حفظ إحصائيات الجيل الحالي
            best = max(self.population, key=lambda g: g.fitness_score)
            worst = min(self.population, key=lambda g: g.fitness_score)
            avg_fitness = statistics.mean(g.fitness_score for g in self.population)
            
            self.logger.info(f"   Best:  {best}")
            self.logger.info(f"   Avg:   {avg_fitness:.2f}")
            self.logger.info(f"   Worst: {worst}")
            
            gen_stats = {
                "generation": gen + 1,
                "best_fitness": best.fitness_score,
                "avg_fitness": avg_fitness,
                "worst_fitness": worst.fitness_score,
                "best_parameters": asdict(best),
            }
            self.evolution_history.append(gen_stats)
            
            # تطوير الجيل التالي
            self.population = self.evolve_generation(self.population)
            self._simulate_fitness_scores()  # تحديث الأداء
        
        # النتيجة النهائية
        best_final = max(self.population, key=lambda g: g.fitness_score)
        
        result = {
            "status": "success",
            "mode": "SHADOW_SIMULATION",
            "live_influence": False,
            "generations_completed": generations,
            "final_best_parameters": asdict(best_final),
            "improvement_over_baseline": {
                "fitness_improvement": (best_final.fitness_score / 7.868) - 1,
                "win_rate_change": best_final.win_rate - 0.64,
                "profit_factor_change": best_final.profit_factor - 4.105,
            },
            "evolution_history": self.evolution_history,
            "timestamp": datetime.now().isoformat()
        }
        
        return result
    
    def _simulate_fitness_scores(self):
        """محاكاة نتائج الأداء (يجب استبدالها بـ backtest فعلي)"""
        for gene in self.population:
            # محاكاة بسيطة: معاملات أقرب للـ baseline تحصل على نتائج أفضل
            risk_factor = abs(gene.risk_percent - 0.5) * 2
            trade_factor = abs(gene.max_trades_per_day - 5) * 0.5
            
            variation = risk_factor + trade_factor + random.random() * 2
            
            gene.win_rate = max(0.50, 0.64 - variation * 0.05)
            gene.profit_factor = max(2.0, 4.105 - variation * 0.3)
            gene.sharpe_ratio = max(3.0, 7.868 - variation * 0.5)
            gene.net_profit = 172388 * gene.profit_factor / 4.105
            gene.fitness_score = self.calculate_fitness(gene)
    
    def save_results(self, result: Dict) -> Path:
        """حفظ نتائج التطور"""
        filename = f"genetic_evolution_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        filepath = self.evolution_dir / filename
        
        with open(filepath, 'w') as f:
            json.dump(result, f, indent=2, ensure_ascii=False)
        
        return filepath
    
    def print_results(self, result: Dict):
        """طباعة نتائج التطور"""
        print("\n" + "="*80)
        print("🧬 GENETIC PARAMETER EVOLUTION RESULTS")
        print("="*80)
        
        best = result["final_best_parameters"]
        print(f"\n🏆 Final Best Parameters:")
        print(f"   Risk: {best['risk_percent']:.1f}%")
        print(f"   Max Trades: {best['max_trades_per_day']}")
        print(f"   TP Multiplier: {best['tp_multiplier']:.1f}x")
        print(f"   SL Multiplier: {best['sl_multiplier']:.1f}x")
        print(f"   Confidence Threshold: {best['confidence_threshold']}%")
        print(f"   Quality Floor: {best['quality_floor']}")
        print(f"   Fitness Score: {best['fitness_score']:.2f}")
        
        impr = result["improvement_over_baseline"]
        print(f"\n📈 Improvement over Baseline:")
        print(f"   Fitness: {impr['fitness_improvement']:+.2%}")
        print(f"   Win Rate: {impr['win_rate_change']:+.2%}")
        print(f"   Profit Factor: {impr['profit_factor_change']:+.2f}")
        
        print(f"\n📊 Evolution History:")
        if result["evolution_history"]:
            for entry in result["evolution_history"][-3:]:  # آخر 3 أجيال
                print(f"   Gen {entry['generation']}: best={entry['best_fitness']:.2f} avg={entry['avg_fitness']:.2f}")
        
        print("\n✅ Results saved to data/analytics/evolution/")
        print("="*80 + "\n")


if __name__ == "__main__":
    engine = ParameterEvolutionEngine(".")
    result = engine.run_evolution_simulation(generations=10)
    filepath = engine.save_results(result)
    engine.print_results(result)
    
    print(f"✅ Genetic evolution complete!")
    print(f"   Results saved to: {filepath}")
