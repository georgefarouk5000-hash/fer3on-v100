from pathlib import Path

from tools.end_to_end_smoke import run_end_to_end_smoke


def test_end_to_end_smoke_reports_success(tmp_path):
    result = run_end_to_end_smoke(root_dir=tmp_path)
    assert result["status"] == "OK"
    assert result["checks"]["python"] is True
