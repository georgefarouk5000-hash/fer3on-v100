import importlib
import os
import tempfile
import unittest
from unittest import mock


class TelegramBotTests(unittest.TestCase):
    def test_health_probe_is_cached_and_uses_api_response(self):
        import core.telegram_bot as telegram_bot

        with mock.patch.object(telegram_bot, "TOKEN", "token"), \
             mock.patch.object(telegram_bot, "BASE_URL", "https://api.telegram.org/bottoken"), \
             mock.patch.object(telegram_bot, "_health_cache", None), \
             mock.patch.object(telegram_bot, "_health_checked_at", 0.0), \
             mock.patch.object(telegram_bot.requests, "get") as mock_get:
            mock_get.return_value.raise_for_status.return_value = None
            mock_get.return_value.json.return_value = {
                "ok": True,
                "result": {"is_bot": True},
            }

            first = telegram_bot.check_telegram_health()
            second = telegram_bot.check_telegram_health()

            self.assertTrue(first["available"])
            self.assertEqual(first, second)
            mock_get.assert_called_once_with(
                "https://api.telegram.org/bottoken/getMe",
                timeout=3,
            )

    def test_get_last_command_omits_offset_when_none(self):
        import core.telegram_bot as telegram_bot

        telegram_bot.TOKEN = "token"
        telegram_bot.CHAT_ID = "chat"
        telegram_bot.BASE_URL = "https://api.telegram.org/bottoken"

        with mock.patch.object(telegram_bot.requests, "get") as mock_get:
            mock_get.return_value.raise_for_status.return_value = None
            mock_get.return_value.json.return_value = {"ok": True, "result": []}

            telegram_bot.get_last_command(None)

            _, kwargs = mock_get.call_args
            self.assertEqual(kwargs["params"], {"timeout": 5})

    def test_import_loads_config_from_repo_root_when_cwd_changes(self):
        repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        with tempfile.TemporaryDirectory() as tmpdir:
            old_cwd = os.getcwd()
            try:
                os.chdir(tmpdir)
                import core.telegram_bot as telegram_bot

                module_path = os.path.abspath(telegram_bot.__file__)
                self.assertTrue(module_path.endswith("core\\telegram_bot.py") or module_path.endswith("core/telegram_bot.py"))
            finally:
                os.chdir(old_cwd)
                importlib.reload(importlib.import_module("core.telegram_bot"))


if __name__ == "__main__":
    unittest.main()
