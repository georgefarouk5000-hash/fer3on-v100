import io
import unittest
from contextlib import redirect_stdout

from core.professional_logging import configure_logging, log_system_event
from core.watchdog import collect_watchdog_status, run_watchdog_cycle


class ProductionIntegrityTests(unittest.TestCase):
    def test_watchdog_reports_healthy_state(self):
        status = collect_watchdog_status(
            mt5_available=True,
            memory_available=True,
            telegram_available=True,
            cpu_ok=True,
            db_ok=True,
        )
        self.assertEqual(status["status"], "HEALTHY")
        self.assertEqual(status["recovery_actions"], [])

    def test_watchdog_cycle_emits_concise_summary(self):
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            run_watchdog_cycle(mt5_available=True, memory_available=True, telegram_available=True)
        text = buffer.getvalue()
        self.assertIn("WATCHDOG", text)
        self.assertIn("HEALTHY", text)

    def test_professional_logging_suppresses_verbose_in_production(self):
        configure_logging("PRODUCTION")
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            log_system_event("routine trace", level="INFO")
            log_system_event("critical error", level="ERROR")
        text = buffer.getvalue()
        self.assertIn("critical error", text)
        self.assertNotIn("routine trace", text)


if __name__ == "__main__":
    unittest.main()
