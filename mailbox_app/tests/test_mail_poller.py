"""Unit tests for mailbox poller service and online user filtering."""

import time
from unittest.mock import patch, MagicMock
from django.test import TestCase, override_settings
from django.core.cache import cache

from customers_app.consumers import get_online_user_ids, REGISTRY_CACHE_KEY
from mailbox_app.services.mail_poller_service import poll_all_active_mailboxes, poll_single_mailbox
from mailbox_app.tasks import poll_mailboxes_unread_task


class MailPollerServiceTestCase(TestCase):
    """Test suite for online user mail polling, circuit breaker cooldown, and Celery lock."""

    def tearDown(self):
        cache.clear()
        super().tearDown()

    def test_get_online_user_ids(self):
        """Verify get_online_user_ids extracts active users and purges expired sessions."""
        now = time.time()
        registry = {
            "channel_active_1": {"user_id": 10, "username": "pilot1", "last_seen": now - 10},
            "channel_active_2": {"user_id": 20, "username": "pilot2", "last_seen": now - 20},
            "channel_expired": {"user_id": 30, "username": "pilot3", "last_seen": now - 120},  # expired > 60s
        }
        cache.set(REGISTRY_CACHE_KEY, registry, timeout=300)

        online_ids = get_online_user_ids()
        self.assertEqual(online_ids, {10, 20})

        # Check that expired session was cleaned up
        updated_registry = cache.get(REGISTRY_CACHE_KEY)
        self.assertIn("channel_active_1", updated_registry)
        self.assertIn("channel_active_2", updated_registry)
        self.assertNotIn("channel_expired", updated_registry)

    @override_settings(MAILBOX_POLL_ONLY_ONLINE_USERS=True)
    def test_poll_all_active_mailboxes_zero_online(self):
        """When 0 users are online, poller should instantly exit without network calls."""
        cache.delete(REGISTRY_CACHE_KEY)

        result = poll_all_active_mailboxes(only_online_users=True)
        self.assertEqual(result["processed"], 0)
        self.assertEqual(result["online_users_count"], 0)
        self.assertGreaterEqual(result["skipped_offline"], 0)
        self.assertEqual(result["errors"], 0)

    def test_circuit_breaker_cooldown(self):
        """Verify broken mailboxes enter cooldown after 2 consecutive errors."""
        mock_acc = MagicMock()
        mock_acc.email = "broken_user@barkol.ru"
        mock_acc.get_password.return_value = "password123"

        with patch("mailbox_app.services.mail_poller_service.ImapMailService") as mock_imap:
            mock_imap.side_effect = Exception("IMAP Auth Failed")

            # First attempt -> error, error count = 1
            res1 = poll_single_mailbox(mock_acc, is_corporate=False)
            self.assertEqual(res1["status"], "error")

            # Second attempt -> error, error count = 2 -> cooldown activated
            res2 = poll_single_mailbox(mock_acc, is_corporate=False)
            self.assertEqual(res2["status"], "error")

            # Third attempt -> skipped due to cooldown!
            res3 = poll_single_mailbox(mock_acc, is_corporate=False)
            self.assertEqual(res3["status"], "skipped")
            self.assertEqual(res3["reason"], "error_cooldown_10m")

    def test_celery_task_concurrency_lock(self):
        """Verify poll_mailboxes_unread_task respects cache lock to prevent overlapping runs."""
        cache.set("celery_lock_poll_mailboxes_unread_task", "locked", timeout=180)

        result = poll_mailboxes_unread_task(only_online=True)
        self.assertEqual(result.get("status"), "skipped")
        self.assertEqual(result.get("reason"), "concurrent_execution_prevented")
