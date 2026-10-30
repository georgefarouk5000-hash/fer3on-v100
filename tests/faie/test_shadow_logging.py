import json
import os
import tempfile
import unittest

from core.unified_decision import DecisionContext
from brain.faie.shadow_logging import build_shadow_decision, log_faie_shadow_decision
from brain.faie.chief_decision_officer import Decision


FORBIDDEN_TOKENS = (
    "trade_executor",
    "execution_optimizer",
    "MetaTrader5",
    "mt5.",
    "order_send",
    "order_close",
    "place_order",
)


class TestShadowLoggingConstitutionalSafety(unittest.TestCase):
    """This file is part of brain/faie — same Volume 1 rule applies: no
    execution capability may ever be introduced here, logging or not."""

    def test_shadow_logging_module_has_no_execution_tokens(self):
        path = os.path.join(os.path.dirname(__file__), "..", "..", "brain", "faie", "shadow_logging.py")
        path = os.path.abspath(path)
        with open(path, "r", encoding="utf-8") as fh:
            lines = fh.readlines()
        code_lines = [ln for ln in lines if not ln.lstrip().startswith("#")]
        content = "".join(code_lines)
        offenders = [tok for tok in FORBIDDEN_TOKENS if tok in content]
        self.assertEqual(offenders, [])


class TestBuildShadowDecision(unittest.TestCase):
    def test_returns_a_decision_object(self):
        ctx = DecisionContext(strategy="SMC", signal="BUY", symbol="XAUUSD", market_regime="TRENDING")
        decision = build_shadow_decision(ctx)
        self.assertIsInstance(decision, Decision)

    def test_uses_personality_profile_for_symbol(self):
        from brain.faie.personality import PERSONALITY_PROFILES
        ctx = DecisionContext(strategy="SMC", signal="BUY", symbol="XAUUSD", market_regime="TRENDING")
        decision = build_shadow_decision(ctx)
        # Every analyst actually weighted in the fused result must be a key
        # XAUUSD's personality profile assigns nonzero weight to — proves
        # the XAUUSD profile (not some other symbol's, and not an accidental
        # equal-weight default) is what fusion actually used.
        used_analysts = set(decision.fused_evidence.weights_used.keys())
        xauusd_analysts = set(PERSONALITY_PROFILES["XAUUSD"].keys())
        self.assertTrue(used_analysts.issubset(xauusd_analysts))
        self.assertTrue(len(used_analysts) > 0)


class TestLogFaieShadowDecision(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.log_path = os.path.join(self._tmpdir.name, "nested", "shadow_log.jsonl")

    def tearDown(self):
        self._tmpdir.cleanup()

    def test_appends_one_json_line_per_call(self):
        ctx = DecisionContext(strategy="DAILY", signal="SELL", symbol="XAUUSD", market_regime="RANGING")
        ok1 = log_faie_shadow_decision(ctx, log_path=self.log_path)
        ok2 = log_faie_shadow_decision(ctx, log_path=self.log_path)
        self.assertTrue(ok1)
        self.assertTrue(ok2)
        with open(self.log_path, "r", encoding="utf-8") as fh:
            lines = [ln for ln in fh.readlines() if ln.strip()]
        self.assertEqual(len(lines), 2)
        row = json.loads(lines[0])
        self.assertIn("faie_decision", row)
        self.assertIn("advisory_label", row["faie_decision"])
        self.assertEqual(row["symbol"], "XAUUSD")

    def test_real_decision_summary_is_included_when_given(self):
        ctx = DecisionContext(strategy="MICRO", signal="BUY", symbol="EURUSD", market_regime="TRENDING")
        log_faie_shadow_decision(
            ctx,
            real_decision_summary={"decision": "FULL", "composite_score": 71.5},
            log_path=self.log_path,
        )
        with open(self.log_path, "r", encoding="utf-8") as fh:
            row = json.loads(fh.readline())
        self.assertEqual(row["real_decision_summary"]["decision"], "FULL")

    def test_never_raises_even_with_a_bad_log_path(self):
        # A path that cannot possibly be created (nested under a file, not
        # a directory) must degrade to `False`, never an exception.
        bad_parent = os.path.join(self._tmpdir.name, "not_a_dir")
        with open(bad_parent, "w", encoding="utf-8") as fh:
            fh.write("i am a file, not a directory")
        bad_path = os.path.join(bad_parent, "shadow_log.jsonl")
        ctx = DecisionContext(strategy="SMC", signal="BUY", symbol="XAUUSD")
        ok = log_faie_shadow_decision(ctx, log_path=bad_path)
        self.assertFalse(ok)

    def test_default_log_path_comes_from_settings(self):
        from core.settings import FAIE_SHADOW_LOG_PATH
        self.assertTrue(FAIE_SHADOW_LOG_PATH.endswith(".jsonl"))


class TestShadowLoggingSettingsFlag(unittest.TestCase):
    def test_flag_defaults_to_true_since_human_approved_enabling_it(self):
        # Enabled by explicit human decision on 2026-07-09 (see
        # docs/FAIE/PHASE_2_PROGRESS.md) so certification.self_audit's
        # bias/drift checks can start accumulating real decision history
        # instead of permanently returning INSUFFICIENT_DATA. Still a pure
        # logging toggle — verify the env var can still override it either
        # way, which is the actual safety property that matters here.
        import importlib
        import core.settings as settings_mod

        os.environ.pop("FAIE_SHADOW_LOGGING_ENABLED", None)
        importlib.reload(settings_mod)
        self.assertTrue(settings_mod.FAIE_SHADOW_LOGGING_ENABLED)

        os.environ["FAIE_SHADOW_LOGGING_ENABLED"] = "False"
        importlib.reload(settings_mod)
        self.assertFalse(settings_mod.FAIE_SHADOW_LOGGING_ENABLED)

        os.environ.pop("FAIE_SHADOW_LOGGING_ENABLED", None)
        importlib.reload(settings_mod)  # restore a clean module state


if __name__ == "__main__":
    unittest.main()
