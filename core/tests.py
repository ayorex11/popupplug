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


class BrevoBackendTests(TestCase):
    @override_settings(BREVO_API_KEY="k", DEFAULT_FROM_EMAIL="PopUp Plug <hello@popupplug.com.ng>")
    def test_posts_to_brevo_api(self):
        from django.core.mail import EmailMultiAlternatives
        from .brevo_backend import BrevoEmailBackend
        m = EmailMultiAlternatives("Hi", "plain", "PopUp Plug <hello@popupplug.com.ng>", ["a@example.com"])
        m.attach_alternative("<b>html</b>", "text/html")
        with mock.patch("core.brevo_backend.requests.post", return_value=mock.Mock(status_code=201, text="")) as post:
            self.assertEqual(BrevoEmailBackend().send_messages([m]), 1)
        body = post.call_args.kwargs["json"]
        self.assertEqual(body["sender"], {"email": "hello@popupplug.com.ng", "name": "PopUp Plug"})
        self.assertEqual((body["to"], body["htmlContent"]), ([{"email": "a@example.com"}], "<b>html</b>"))
        self.assertEqual(post.call_args.kwargs["headers"]["api-key"], "k")

    @override_settings(BREVO_API_KEY="k")
    def test_api_error_raises(self):
        from django.core.mail import EmailMessage
        from .brevo_backend import BrevoEmailBackend
        with mock.patch("core.brevo_backend.requests.post", return_value=mock.Mock(status_code=401, text="bad key")):
            with self.assertRaises(RuntimeError):
                BrevoEmailBackend().send_messages([EmailMessage("x", "y", "a@b.com", ["c@d.com"])])