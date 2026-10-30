#!/usr/bin/env python3
# =========================================
# FER3ON V5.6 — ML TRAINING RUNNER
# يدرّب GBM + NN + يعرض RL statistics
# Usage: python run_ml_train.py [--analyze]
# =========================================

import sys, os, argparse
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def main():
    parser = argparse.ArgumentParser(description="FER3ON V5.6 ML Trainer")
    parser.add_argument("--analyze", action="store_true", help="تحليل Trade DNA فقط بدون تدريب")
    parser.add_argument("--force",   action="store_true", help="إجبار التدريب حتى لو بيانات قليلة")
    args = parser.parse_args()

    from brain.trade_dna      import load_trade_dna, FEATURE_NAMES
    from ml.xgboost_model     import train_from_dna, get_gbm_predictor
    from ml.neural_network    import train_nn_from_dna, get_nn_predictor
    from ml.reinforcement     import get_qtable
    from ml.ml_orchestrator   import retrain_all_models
    from testing.statistics   import full_stats_analysis, format_stats_report

    dna = load_trade_dna()
    print(f"\n{'='*50}")
    print(f"  FER3ON V5.6 ML TRAINING")
    print(f"  Trade DNA records: {len(dna)}")
    print(f"{'='*50}\n")

    # ————————————————————————
    # DNA Analysis
    # ————————————————————————
    if dna:
        wins   = sum(1 for t in dna if t.get("result")=="WIN")
        losses = sum(1 for t in dna if t.get("result")=="LOSS")
        print(f"  Wins:   {wins}")
        print(f"  Losses: {losses}")
        print(f"  Win Rate: {round(wins/(wins+losses)*100,1) if (wins+losses)>0 else 0}%")

        # Feature distribution
        print(f"\n  Top Quality Scores:")
        q_scores = [t.get("quality_score",0) for t in dna]
        if q_scores:
            import numpy as np
            print(f"    Mean:   {np.mean(q_scores):.1f}")
            print(f"    Median: {np.median(q_scores):.1f}")
            print(f"    90th:   {np.percentile(q_scores,90):.1f}")

        print(f"\n  Strategy Distribution:")
        from collections import Counter
        strats = Counter(t.get("strategy","?") for t in dna)
        for s, cnt in strats.most_common():
            print(f"    {s}: {cnt}")

    if args.analyze:
        print("\n  [ANALYZE ONLY MODE — no training]")
        return

    if len(dna) < 30 and not args.force:
        print(f"\n⚠️  Only {len(dna)} records. Need 30+ for training.")
        print("   Use --force to train anyway, or wait for more trades.")
        return

    # ————————————————————————
    # TRAIN
    # ————————————————————————
    print(f"\n🔬 Training GBM + Neural Network...")
    result = retrain_all_models()

    print(f"\n{'='*50}")
    print(f"  ✅ TRAINING RESULTS")
    print(f"{'='*50}")

    gbm_r = result.get("gbm", {})
    nn_r  = result.get("nn", {})

    print(f"  GBM ({gbm_r.get('engine','GradientBoosting')}):")
    print(f"    Trained:  {gbm_r.get('trained')}")
    print(f"    Samples:  {gbm_r.get('n_samples',0)}")
    print(f"    CV AUC:   {gbm_r.get('cv_auc',0)}")
    print(f"    Win Rate: {gbm_r.get('win_rate',0)}%")
    if gbm_r.get("top_features"):
        print(f"    Top Features:")
        for feat, imp in gbm_r.get("top_features",{}).items():
            print(f"      {feat}: {imp:.4f}")

    print(f"\n  Neural Network (64→32→16):")
    print(f"    Trained:  {nn_r.get('trained')}")
    print(f"    Samples:  {nn_r.get('n_samples',0)}")
    print(f"    CV AUC:   {nn_r.get('cv_auc',0)}")

    # RL Stats
    qt = get_qtable()
    qt_s = qt.get_stats()
    print(f"\n  Reinforcement Learning (Q-Table):")
    print(f"    States:   {qt_s['n_states']}")
    print(f"    Updates:  {qt_s['total_updates']}")
    print(f"    Epsilon:  {qt_s['epsilon']}")

    # Full Stats
    print(f"\n  Live Performance Statistics:")
    try:
        stats = full_stats_analysis()
        print(format_stats_report(stats))
    except Exception as e:
        print(f"  ⚠️  Stats error: {e}")

    print(f"\n{'='*50}")
    print(f"  Models saved to: data/models/")
    print(f"{'='*50}\n")


if __name__ == "__main__":
    main()
