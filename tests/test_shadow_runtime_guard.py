import os
import subprocess
import sys


def test_shadow_runtime_settings_are_explicitly_available():
    env = dict(os.environ)
    env["FER3ON_SHADOW_ONLY"] = "True"
    env["FER3ON_SHADOW_MAX_CYCLES"] = "3"
    result = subprocess.run(
        [sys.executable, "-c", "from core.settings import SHADOW_ONLY_RUNTIME, SHADOW_RUN_MAX_CYCLES; print(SHADOW_ONLY_RUNTIME, SHADOW_RUN_MAX_CYCLES)"],
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )
    assert "True 3" in result.stdout