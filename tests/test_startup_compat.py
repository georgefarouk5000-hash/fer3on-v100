import importlib.util
import os
import sys
import types
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)

execution_pkg_path = os.path.join(ROOT, "execution")
if "execution" not in sys.modules:
    execution_pkg = types.ModuleType("execution")
    execution_pkg.__path__ = [execution_pkg_path]
    sys.modules["execution"] = execution_pkg

spec = importlib.util.spec_from_file_location(
    "execution.scale_in",
    os.path.join(execution_pkg_path, "scale_in.py"),
)
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)

from core.startup_check import run_startup_check


class StartupCompatibilityTests(unittest.TestCase):
    def test_startup_check_exposes_required_runtime_functions(self):
        summary = run_startup_check(strict=False)
        critical = summary.get("critical_functions", {})

        self.assertEqual(summary.get("system_status"), "SYSTEM_READY")
        self.assertEqual(critical["core.risk_protection"].get("status"), "ACTIVE")
        self.assertEqual(critical["core.confidence_engine"].get("status"), "ACTIVE")
        self.assertEqual(critical["core.trailing_stop"].get("status"), "ACTIVE")


if __name__ == "__main__":
    unittest.main()
