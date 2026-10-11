import os
from io import StringIO
from unittest import mock

from django.contrib.auth import get_user_model
from django.core import mail
from django.core.management import call_command
from django.test import TestCase, override_settings

User = get_user_model()


class CoreTests(TestCase):
    def test_healthz_any_host(self):
        for path in ("/healthz", "/healthz/"):
            r = self.client.get(path, HTTP_HOST="10.1.2.3")
            self.assertEqual((r.status_code, r.content), (200, b"ok"))

    def test_ensure_admin_creates_then_updates(self):
        env = {"ADMIN_EMAIL": "Boss@Example.com", "ADMIN_PASSWORD": "pw-12345-xyz"}
        with mock.patch.dict(os.environ, env):
            call_command("ensure_admin", stdout=StringIO())
            call_command("ensure_admin", stdout=StringIO())
        u = User.objects.get()
        self.assertEqual((u.username, u.is_staff, u.is_superuser), ("boss@example.com", True, True))
        self.assertTrue(u.check_password("pw-12345-xyz"))

    def test_ensure_admin_skips_without_env(self):
        with mock.patch.dict(os.environ, {"ADMIN_EMAIL": ""}):
            call_command("ensure_admin", stdout=StringIO())
        self.assertFalse(User.objects.exists())

    @override_settings(NOTIFY_ASYNC=False, ADMIN_NOTIFY_EMAILS=[])
    def test_admin_recipients_fall_back_to_staff(self):
        from .notifications import admin_recipients
        User.objects.create_user("s", "staff@example.com", "x", is_staff=True)
        User.objects.create_user("n", "normal@example.com", "x")
        self.assertEqual(admin_recipients(), ["staff@example.com"])

    @override_settings(NOTIFY_ASYNC=False)
    def test_test_email_command(self):
        with self.captureOnCommitCallbacks(execute=True):
            call_command("send_test_email", "a@example.com", stdout=StringIO())
        self.assertEqual(mail.outbox[0].to, ["a@example.com"])

    def test_bootstrap_is_repeatable(self):
        with mock.patch.dict(os.environ, {"ADMIN_EMAIL": "", "ADMIN_PASSWORD": ""}):
            call_command("bootstrap", stdout=StringIO())
            call_command("bootstrap", stdout=StringIO())
