import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from core import env_utils


class EnvUtilsTests(unittest.TestCase):
    def test_load_project_env_uses_repo_root_path(self):
        repo_root = Path(__file__).resolve().parents[1]
        expected_env = repo_root / "config.env"

        with tempfile.TemporaryDirectory() as tmpdir:
            old_cwd = os.getcwd()
            try:
                os.chdir(tmpdir)
                with mock.patch("core.env_utils._load_dotenv") as mock_load_dotenv:
                    resolved = env_utils.load_project_env(repo_root / "main.py")
                    mock_load_dotenv.assert_called_once_with(expected_env)
                    self.assertEqual(resolved, expected_env)
            finally:
                os.chdir(old_cwd)


if __name__ == "__main__":
    unittest.main()
