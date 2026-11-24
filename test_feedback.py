import unittest
from types import SimpleNamespace
from unittest.mock import patch

import requests

from feedback import build_report
from notifier import (
    _normalize_config, send_feedback, send_error_alert, send_inspection_status, send_success_report,
)


class FeedbackTest(unittest.TestCase):
    def test_support_is_opt_in_and_not_a_success_recipient(self):
        cfg = _normalize_config({"bot_token": "fake", "chat_id": "-123", "enabled": True,
                                 "feedback_chat_id": "456"})
        with patch("notifier.load_telegram_config", return_value=cfg), patch("notifier.requests.post") as post:
            post.return_value.status_code = 200
            post.return_value.json.return_value = {"ok": True}
            def messages():
                return [c.kwargs["json"] for c in post.call_args_list]
            send_error_alert("raw-secret", template="ACE", site="02041")
            self.assertEqual([m["chat_id"] for m in messages()], ["-123"])
            post.reset_mock()
            cfg["auto_support_errors"] = True
            send_error_alert("raw-secret (find assigned card)", template="ACE", site="02041")
            self.assertEqual([m["chat_id"] for m in messages()], ["-123", "456"])
            self.assertIn("02041", messages()[1]["text"])
            self.assertNotIn("raw-secret", messages()[1]["text"])
            post.reset_mock()
            send_success_report("ACE", "02041", 42, 0, verified=True)
            self.assertEqual([m["chat_id"] for m in messages()], ["-123"])

    def test_vons_notifications_go_only_to_vons_chat(self):
        cfg = _normalize_config({"bot_token": "yummi-bot", "chat_id": "-111", "enabled": True,
                                 "vons_chat_ids": "-222, -333"})
        with patch("notifier.load_telegram_config", return_value=cfg), patch("notifier.requests.post") as post:
            post.return_value.status_code = 200
            def chats():
                return [c.kwargs["json"]["chat_id"] for c in post.call_args_list]
            send_inspection_status("RUNNING", "ACE", "VONS 02041 (Main)", account="von02041")
            send_success_report("ACE", "VONS 02090 (Main)", 42, 0, account="ace_vons_02090")
            send_error_alert("boom", template="ACE", site="VONS 02090 (Main)")
            self.assertEqual(chats(), ["-222", "-333"] * 3)
            self.assertEqual({c.args[0] for c in post.call_args_list}, {"https://api.telegram.org/botyummi-bot/sendMessage"})
            post.reset_mock()
            # Yummi store whose name also contains "VONS" stays on the Yummi chat.
            send_inspection_status("RUNNING", "Yummi Sushi - 5PM Case Photos", "GBC ABS-VONS 0724", account="yummi")
            send_error_alert("boom", template="Yummi", site="GBC ABS-VONS 0724")
            self.assertEqual(chats(), ["-111", "-111"])
            post.reset_mock()
            cfg = _normalize_config({"bot_token": "yummi-bot", "chat_id": "-111", "enabled": True,
                                     "vons_bot_token": "vons-bot", "vons_chat_ids": "-222"})
        with patch("notifier.load_telegram_config", return_value=cfg), patch("notifier.requests.post") as post:
            post.return_value.status_code = 200
            send_inspection_status("RUNNING", "ACE", "VONS 02041 (Main)", account="von02041")
            self.assertEqual(post.call_args.args[0], "https://api.telegram.org/botvons-bot/sendMessage")
            self.assertEqual(post.call_args.kwargs["json"]["chat_id"], "-222")
        # No VONS chat configured: keep the old behaviour (everything to the main chat).
        cfg = _normalize_config({"bot_token": "yummi-bot", "chat_id": "-111", "enabled": True})
        with patch("notifier.load_telegram_config", return_value=cfg), patch("notifier.requests.post") as post:
            post.return_value.status_code = 200
            send_inspection_status("RUNNING", "ACE", "VONS 02041 (Main)", account="von02041")
            self.assertEqual(post.call_args.kwargs["json"]["chat_id"], "-111")

    def test_report_does_not_copy_log_text_or_secrets(self):
        report = build_report(
            "2.7.2",
            {"current_template": "ACE", "current_site": "VONS 02090 (Main)",
             "current_account": "von02090", "scheduled_time": "13:00",
             "password": "password-secret", "data_file": "secret-path"},
            "Select Your Store",
            [{"success": False, "errors": ["Next page not found token-secret", "url-secret"]}],
            [SimpleNamespace(run_time="13:15", site_location="VONS 02041 (Main)",
                             account_name="von02041", template_name="ACE")],
        )
        for value in ("ACE", "13:00", "13:15", "von02090", "von02041", "page navigation"):
            self.assertIn(value, report)
        self.assertNotIn("secret", report)

    def test_only_configured_private_destination_receives_feedback(self):
        cfg = _normalize_config({
            "bot_token": "fake-token", "chat_id": "-123", "feedback_chat_id": "456",
            "enabled": True,
        })
        with patch("notifier.load_telegram_config", return_value=cfg), patch("notifier.requests.post") as post:
            post.return_value.status_code = 200
            post.return_value.json.return_value = {"ok": True}
            self.assertFalse(send_feedback("report", "-123"))
            post.assert_not_called()
            self.assertTrue(send_feedback("report", "456"))
            self.assertEqual(post.call_args.kwargs["json"], {"chat_id": "456", "text": "report"})
            post.side_effect = requests.Timeout("https://example.com/fake-token")
            with self.assertLogs("notifier", level="WARNING") as logs:
                self.assertFalse(send_feedback("report", "456"))
            self.assertNotIn("fake-token", "\n".join(logs.output))


if __name__ == "__main__":
    unittest.main()
