import unittest
from datetime import datetime, timezone

from core.unified_bridge import build_decision_context


class TestBuildDecisionContextExecutionGrade(unittest.TestCase):
    """Regression coverage for a bug found via live log inspection: a real
    run's 'SMART DECISION AUTHORITY' report showed 'Execution Grade :
    UNKNOWN' on every single cycle, even when EXEC INTELLIGENCE and
    SMC_ENTRY had both computed a real grade (B, B+, ...) moments earlier
    in the same log. Root cause: build_decision_context() (the live call
    site in main.py included) never had an execution_grade parameter, so
    DecisionContext.execution_grade always fell back to its 'UNKNOWN'
    default -- silently disabling _is_high_execution_context()'s
    A/A+/ELITE bonus path entirely, and always tripping the VOLATILE-
    regime execution penalty meant only for genuinely poor/unknown
    execution.
    """

    def test_execution_grade_is_passed_through(self):
        ctx = build_decision_context(strategy="SMC", signal="BUY", execution_grade="A+")
        self.assertEqual(ctx.execution_grade, "A+")

    def test_execution_grade_defaults_to_unknown_when_omitted(self):
        ctx = build_decision_context(strategy="SMC", signal="BUY")
        self.assertEqual(ctx.execution_grade, "UNKNOWN")

    def test_execution_grade_is_uppercased(self):
        ctx = build_decision_context(strategy="SMC", signal="BUY", execution_grade="b+")
        self.assertEqual(ctx.execution_grade, "B+")

    def test_high_execution_context_reachable_with_real_grade(self):
        # Before the fix, this path was permanently unreachable in live
        # trading no matter how good execution quality actually was,
        # because execution_grade could never be anything but 'UNKNOWN'.
        from core.unified_decision import _is_high_execution_context

        ctx = build_decision_context(
            strategy="SMC", signal="BUY", execution_grade="A+",
            execution_score=70.0, spread_ratio=0.05,
            candle_trigger_confirmed=True, liquidity_alignment=80.0,
        )
        self.assertTrue(_is_high_execution_context(ctx))


class TestBuildDecisionContextHourWiring(unittest.TestCase):
    def test_explicit_hour_and_minute_are_used_as_given(self):
        ctx = build_decision_context(strategy="SMC", signal="BUY", hour=9, minute=42)
        self.assertEqual(ctx.hour, 9)
        self.assertEqual(ctx.minute, 42)

    def test_omitted_hour_defaults_to_real_current_utc_hour(self):
        before = datetime.now(timezone.utc)
        ctx = build_decision_context(strategy="SMC", signal="BUY")
        after = datetime.now(timezone.utc)
        # ctx.hour must be a real UTC hour taken from "now", not None and
        # not a placeholder — bounded by the UTC hour(s) this test actually
        # ran in (guards against a timezone/units bug without being flaky
        # around an hour boundary).
        self.assertIsNotNone(ctx.hour)
        self.assertIn(ctx.hour, {before.hour, after.hour})

    def test_hour_without_explicit_minute_defaults_minute_to_zero(self):
        ctx = build_decision_context(strategy="SMC", signal="BUY", hour=14)
        self.assertEqual(ctx.hour, 14)
        self.assertEqual(ctx.minute, 0)

    def test_returned_context_is_usable_by_session_analyst(self):
        from brain.faie.analysts import SessionAnalyst
        ctx = build_decision_context(strategy="SMC", signal="BUY", hour=9, minute=15)
        report = SessionAnalyst().analyze(ctx)
        self.assertFalse(report.partial)
        self.assertIn("london_sweep", report.evidence[0].tags)


if __name__ == "__main__":
    unittest.main()
