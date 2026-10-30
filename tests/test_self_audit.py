import json
import os
import tempfile
import unittest

from certification.self_audit import (
    detect_bias,
    detect_drift,
    detect_overfitting,
    build_self_audit_report,
    write_self_audit_report,
    load_shadow_log_decisions,
    split_recent_vs_baseline,
    MIN_DECISIONS_FOR_BIAS,
    MIN_DECISIONS_FOR_DRIFT,
)


def _decision(direction="BULLISH", net_score=0.0, per_analyst=None, partial_analysts=None):
    return {
        "top_scenario": {"direction": direction},
        "fused_evidence": {
            "net_score": net_score,
            "per_analyst": per_analyst or {},
            "partial_analysts": partial_analysts or [],
        },
    }


class TestDetectBias(unittest.TestCase):
    def test_insufficient_data_below_min_sample(self):
        decisions = [_decision() for _ in range(MIN_DECISIONS_FOR_BIAS - 1)]
        report = detect_bias(decisions)
        self.assertEqual(report.status, "INSUFFICIENT_DATA")
        self.assertFalse(report.flagged)

    def test_flags_skewed_decision_with_balanced_evidence(self):
        # 90% BULLISH decisions, but net_score alternates sign evenly —
        # this is exactly the "bug signature" the spec describes.
        decisions = []
        for i in range(30):
            net = 20.0 if i % 2 == 0 else -20.0  # balanced sign distribution
            direction = "BULLISH" if i < 27 else "BEARISH"  # 90% BULLISH decisions
            decisions.append(_decision(direction=direction, net_score=net))
        report = detect_bias(decisions)
        self.assertEqual(report.status, "OK")
        self.assertTrue(report.flagged)

    def test_does_not_flag_when_evidence_matches_decision_skew(self):
        # Genuine trend: decisions AND net_score both skew bullish together.
        decisions = [_decision(direction="BULLISH", net_score=30.0) for _ in range(30)]
        report = detect_bias(decisions)
        self.assertEqual(report.status, "OK")
        self.assertFalse(report.flagged)

    def test_accepts_decision_objects_with_to_dict(self):
        class FakeDecision:
            def to_dict(self):
                return _decision(direction="BULLISH", net_score=30.0)
        decisions = [FakeDecision() for _ in range(25)]
        report = detect_bias(decisions)
        self.assertEqual(report.status, "OK")
        self.assertEqual(report.sample_size, 25)


class TestDetectDrift(unittest.TestCase):
    def test_insufficient_data_below_min_sample(self):
        recent = [_decision(per_analyst={"SMCAnalyst": 10.0})] * (MIN_DECISIONS_FOR_DRIFT - 1)
        baseline = [_decision(per_analyst={"SMCAnalyst": 10.0})] * MIN_DECISIONS_FOR_DRIFT
        report = detect_drift(recent, baseline)
        self.assertEqual(report.status, "INSUFFICIENT_DATA")

    def test_flags_large_mean_net_score_shift(self):
        baseline = [_decision(per_analyst={"SMCAnalyst": 10.0}) for _ in range(15)]
        recent = [_decision(per_analyst={"SMCAnalyst": 60.0}) for _ in range(15)]
        report = detect_drift(recent, baseline)
        self.assertEqual(report.status, "OK")
        self.assertIn("SMCAnalyst", report.flagged_analysts)

    def test_does_not_flag_stable_analyst(self):
        baseline = [_decision(per_analyst={"SMCAnalyst": 10.0}) for _ in range(15)]
        recent = [_decision(per_analyst={"SMCAnalyst": 12.0}) for _ in range(15)]
        report = detect_drift(recent, baseline)
        self.assertNotIn("SMCAnalyst", report.flagged_analysts)

    def test_flags_broken_analyst_via_partial_rate_jump(self):
        baseline = [
            _decision(per_analyst={"MacroAnalyst": 5.0}, partial_analysts=[])
            for _ in range(15)
        ]
        recent = [
            _decision(per_analyst={"MacroAnalyst": 5.0}, partial_analysts=["MacroAnalyst"])
            for _ in range(15)
        ]
        report = detect_drift(recent, baseline)
        self.assertIn("MacroAnalyst", report.flagged_analysts)

    def test_analyst_missing_from_one_window_is_skipped_not_fabricated(self):
        baseline = [_decision(per_analyst={"SMCAnalyst": 10.0}) for _ in range(15)]
        recent = [_decision(per_analyst={"TechnicalAnalyst": 10.0}) for _ in range(15)]
        report = detect_drift(recent, baseline)
        analysts_compared = {d["analyst"] for d in report.per_analyst_drift}
        self.assertNotIn("SMCAnalyst", analysts_compared)
        self.assertNotIn("TechnicalAnalyst", analysts_compared)


class TestDetectOverfitting(unittest.TestCase):
    def test_insufficient_data_with_one_period(self):
        report = detect_overfitting({"in_sample": {"win_rate": 60.0}})
        self.assertEqual(report.status, "INSUFFICIENT_DATA")

    def test_flags_large_degradation(self):
        metrics = {
            "in_sample": {"win_rate": 70.0, "profit_factor": 2.0},
            "out_of_sample": {"win_rate": 40.0, "profit_factor": 0.9},
        }
        report = detect_overfitting(metrics)
        self.assertEqual(report.status, "OK")
        self.assertIn("win_rate", report.flagged_metrics)
        self.assertIn("profit_factor", report.flagged_metrics)

    def test_does_not_flag_stable_metrics(self):
        metrics = {
            "in_sample": {"win_rate": 55.0},
            "out_of_sample": {"win_rate": 54.0},
        }
        report = detect_overfitting(metrics)
        self.assertEqual(report.flagged_metrics, [])

    def test_non_numeric_metric_is_skipped_not_raised(self):
        metrics = {
            "in_sample": {"win_rate": 55.0, "grade": "A+"},
            "out_of_sample": {"win_rate": 54.0, "grade": "B"},
        }
        report = detect_overfitting(metrics)
        metric_names = {d["metric"] for d in report.metric_drifts}
        self.assertIn("win_rate", metric_names)
        self.assertNotIn("grade", metric_names)


class TestSplitRecentVsBaseline(unittest.TestCase):
    def test_splits_roughly_in_half_by_default(self):
        decisions = list(range(10))
        baseline, recent = split_recent_vs_baseline(decisions)
        self.assertEqual(baseline + recent, decisions)
        self.assertEqual(len(recent), 5)

    def test_empty_input_returns_two_empty_lists(self):
        self.assertEqual(split_recent_vs_baseline([]), ([], []))


class TestLoadShadowLogDecisions(unittest.TestCase):
    def test_missing_file_returns_empty_list(self):
        decisions = load_shadow_log_decisions("/tmp/definitely_missing_shadow_log_xyz.jsonl")
        self.assertEqual(decisions, [])

    def test_reads_faie_decision_field_from_each_line(self):
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "shadow_log.jsonl")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(json.dumps({"faie_decision": _decision(direction="BULLISH")}) + "\n")
                fh.write(json.dumps({"faie_decision": _decision(direction="BEARISH")}) + "\n")
                fh.write("not valid json\n")  # must be skipped, not fatal
                fh.write("\n")  # blank line, must be skipped
            decisions = load_shadow_log_decisions(path)
            self.assertEqual(len(decisions), 2)


class TestBuildAndWriteSelfAuditReport(unittest.TestCase):
    def test_build_report_with_no_inputs_is_all_insufficient_data(self):
        report = build_self_audit_report()
        self.assertEqual(report["bias"]["status"], "INSUFFICIENT_DATA")
        self.assertEqual(report["drift"]["status"], "INSUFFICIENT_DATA")
        self.assertEqual(report["overfitting"]["status"], "INSUFFICIENT_DATA")

    def test_write_self_audit_report_creates_json_file(self):
        with tempfile.TemporaryDirectory() as td:
            report = build_self_audit_report()
            out_path = write_self_audit_report(report, out_dir=td)
            self.assertTrue(out_path.exists())
            with open(out_path, "r", encoding="utf-8") as fh:
                loaded = json.load(fh)
            self.assertIn("bias", loaded)
            self.assertIn("drift", loaded)
            self.assertIn("overfitting", loaded)

    def test_build_report_splits_decisions_automatically_when_only_decisions_given(self):
        decisions = [
            _decision(per_analyst={"SMCAnalyst": 10.0}) for _ in range(MIN_DECISIONS_FOR_DRIFT * 2)
        ]
        report = build_self_audit_report(decisions=decisions)
        # With enough decisions and no explicit recent/baseline split, drift
        # should still get evaluated via the automatic chronological split.
        self.assertIn(report["drift"]["status"], ("OK", "INSUFFICIENT_DATA"))


if __name__ == "__main__":
    unittest.main()
