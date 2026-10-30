from tools.system_health_check import run_health_check


def test_health_check_creates_runtime_directories(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result = run_health_check()
    assert result["score"] >= 0
    runtime_dirs = [item["name"] for item in result["checks"] if item["name"].startswith("dir:runtime")]
    assert runtime_dirs
