from datetime import timedelta
from unittest import mock

from django.contrib.auth import get_user_model
from django.core import mail
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from events.models import Area, Category, Event
from events.tests import make_image
from social.models import SocialPost
from vendors.models import Vendor

User = get_user_model()
SIGNUP = {"email": "Ada@Example.com", "password1": "a-Strong-pass-123", "password2": "a-Strong-pass-123",
          "name": "Ada Bakes", "phone": "08031234567", "instagram": "@adabakes", "twitter": ""}


@override_settings(NOTIFY_ASYNC=False, ADMIN_NOTIFY_EMAILS=["boss@example.com"], INSTAGRAM_ENABLED=True,
                   INSTAGRAM_AUTOPOST=False, INSTAGRAM_DRY_RUN=False, SITE_URL="https://popupplug.com.ng")
class DeskFlowTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_lagos", verbosity=0)
        cls.staff = User.objects.create_user("boss@example.com", "boss@example.com", "pw-12345-xyz", is_staff=True)

    def signup(self):
        with self.captureOnCommitCallbacks(execute=True):
            self.client.post(reverse("vendors:signup"), SIGNUP)
        self.client.logout()

    def test_signup_emails_admin_with_desk_link(self):
        self.signup()
        self.assertEqual(len(mail.outbox), 1)
        msg = mail.outbox[0]
        self.assertEqual(msg.to, ["boss@example.com"])
        self.assertIn("Ada Bakes", msg.subject)
        self.assertIn("https://popupplug.com.ng/desk/vendors/?tab=pending", msg.body)
        self.assertTrue(User.objects.filter(username="ada@example.com").exists())  # email is the username

    def test_signup_then_login_with_email_any_case(self):
        self.signup()
        self.assertTrue(self.client.login(username="ada@example.com", password="a-Strong-pass-123"))
        r = self.client.post(reverse("login"), {"username": " ADA@example.com ", "password": "a-Strong-pass-123"})
        self.assertEqual(r.status_code, 302)

    def test_desk_requires_staff(self):
        for name in ("desk:home", "desk:vendors", "desk:events", "desk:social"):
            self.assertEqual(self.client.get(reverse(name)).status_code, 302)
        self.signup()
        self.client.login(username="ada@example.com", password="a-Strong-pass-123")
        self.assertEqual(self.client.get(reverse("desk:home")).status_code, 302)  # vendors are not staff
        v = Vendor.objects.get()
        r = self.client.post(reverse("desk:vendor_action", args=[v.pk]), {"action": "approve"})
        self.assertEqual(r.status_code, 302)
        v.refresh_from_db()
        self.assertFalse(v.verified)

    def test_approve_vendor_emails_vendor_and_queues_welcome_card(self):
        self.signup()
        mail.outbox.clear()
        v = Vendor.objects.get()
        self.client.force_login(self.staff)
        self.assertContains(self.client.get(reverse("desk:vendors") + "?tab=pending"), "Ada Bakes")
        with self.captureOnCommitCallbacks(execute=True):
            self.client.post(reverse("desk:vendor_action", args=[v.pk]), {"action": "approve", "next": "/desk/vendors/?tab=pending"})
        v.refresh_from_db()
        self.assertTrue(v.verified)
        self.assertEqual(mail.outbox[0].to, ["ada@example.com"])
        self.assertEqual(SocialPost.objects.filter(kind="welcome", vendor=v).count(), 1)
        self.assertContains(self.client.get(reverse("desk:social")), "Ada Bakes")

    def _pending_event(self):
        self.signup()
        v = Vendor.objects.get()
        start = timezone.now() + timedelta(days=3)
        e = Event.objects.create(vendor=v, title="Ada Cake Day", category=Category.objects.first(), area=Area.objects.get(slug="lekki"),
                                 venue="12 Admiralty Way", description="Cakes", start_at=start, end_at=start + timedelta(hours=5))
        e.cover_image.save("c.png", make_image(size=(900, 700)), save=True)
        return e

    def test_approve_event_publishes_emails_and_queues_instagram(self):
        e = self._pending_event()
        mail.outbox.clear()
        self.client.force_login(self.staff)
        with self.captureOnCommitCallbacks(execute=True):
            self.client.post(reverse("desk:event_action", args=[e.pk]), {"action": "approve"})
        e.refresh_from_db()
        self.assertEqual(e.status, "published")
        self.assertIn("live", mail.outbox[0].subject)
        post = SocialPost.objects.get(event=e)
        self.assertIn("Ada Cake Day", post.caption)
        self.assertTrue(post.image.name.endswith(".jpg"))

    def test_reject_event_sends_reason(self):
        e = self._pending_event()
        mail.outbox.clear()
        self.client.force_login(self.staff)
        with self.captureOnCommitCallbacks(execute=True):
            self.client.post(reverse("desk:event_action", args=[e.pk]), {"action": "reject", "note": "Please add a real venue"})
        e.refresh_from_db()
        self.assertEqual((e.status, e.review_note), ("rejected", "Please add a real venue"))
        self.assertIn("Please add a real venue", mail.outbox[0].body)

    def test_suspend_hides_events(self):
        e = self._pending_event()
        Event.objects.filter(pk=e.pk).update(status="published")
        self.client.force_login(self.staff)
        self.client.post(reverse("desk:vendor_action", args=[e.vendor.pk]), {"action": "suspend"})
        e.refresh_from_db()
        self.assertEqual(e.status, "rejected")
        e.vendor.user.refresh_from_db()
        self.assertFalse(e.vendor.user.is_active)

    def test_new_pending_event_emails_admin(self):
        self.signup()
        mail.outbox.clear()
        self.client.login(username="ada@example.com", password="a-Strong-pass-123")
        start = timezone.localtime(timezone.now() + timedelta(days=3)).replace(second=0, microsecond=0)
        with self.captureOnCommitCallbacks(execute=True):
            r = self.client.post(reverse("events:create"), {
                "title": "Fresh Pop", "category": Category.objects.filter(is_general=False).first().pk, "area": Area.objects.get(slug="lekki").pk,
                "venue": "12 Admiralty Way", "description": "x", "start_at": start.strftime("%Y-%m-%dT%H:%M"),
                "end_at": (start + timedelta(hours=4)).strftime("%Y-%m-%dT%H:%M"), "is_free_entry": "on", "cover_image": make_image(),
            })
        self.assertEqual(r.status_code, 302)
        self.assertEqual(mail.outbox[0].to, ["boss@example.com"])
        self.assertIn("Fresh Pop", mail.outbox[0].subject)

    def test_desk_pages_render(self):
        self._pending_event()
        self.client.force_login(self.staff)
        for name in ("desk:home", "desk:vendors", "desk:events", "desk:social"):
            self.assertEqual(self.client.get(reverse(name)).status_code, 200, name)
        self.assertContains(self.client.get(reverse("desk:events") + "?tab=pending"), "Ada Cake Day")

    def test_email_failure_never_breaks_signup(self):
        with mock.patch("core.notifications.EmailMultiAlternatives.send", side_effect=OSError("smtp down")):
            with self.captureOnCommitCallbacks(execute=True):
                r = self.client.post(reverse("vendors:signup"), SIGNUP)
        self.assertEqual(r.status_code, 302)
        self.assertTrue(Vendor.objects.exists())
