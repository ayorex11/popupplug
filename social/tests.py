from datetime import timedelta
from unittest import mock

from django.core.management import call_command
from django.test import TestCase, override_settings
from django.contrib.auth import get_user_model
from django.utils import timezone
from PIL import Image

from events.models import Area, Category, Event
from events.tests import make_image
from vendors.models import Vendor

from . import cards, instagram, services
from .models import InstagramToken, SocialPost

User = get_user_model()


@override_settings(NOTIFY_ASYNC=False, INSTAGRAM_ENABLED=True, INSTAGRAM_USER_ID="123", INSTAGRAM_ACCESS_TOKEN="SECRET123",
                   SITE_URL="https://popupplug.com.ng", INSTAGRAM_DRY_RUN=False, INSTAGRAM_AUTOPOST=False)
class InstagramTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_lagos", verbosity=0)
        u = User.objects.create_user("v@example.com", "v@example.com", "pw-12345-xyz")
        cls.vendor = Vendor.objects.create(user=u, name="A Very Long Vendor Name For Wrapping Tests Ltd", phone="08011111111", instagram="vend", verified=True)
        start = timezone.now() + timedelta(days=2)
        cls.event = Event.objects.create(vendor=cls.vendor, title="A Rather Long Event Title That Needs To Wrap Across Lines Nicely",
            category=Category.objects.first(), area=Area.objects.get(slug="lekki"), venue="12 Admiralty Way, Lekki",
            description="d", start_at=start, end_at=start + timedelta(hours=5), status="published")
        cls.event.cover_image.save("c.png", make_image(size=(1200, 900)), save=True)

    def test_cards_are_1080x1350_jpegs(self):
        for f in (cards.render_event_card(self.event), cards.render_welcome_card(self.vendor)):
            img = Image.open(f)
            self.assertEqual((img.size, img.format), ((1080, 1350), "JPEG"))

    def test_caption_has_link_and_vendor_handle(self):
        c = cards.event_caption(self.event)
        self.assertIn("https://popupplug.com.ng/e/", c)
        self.assertIn("@vend", c)

    def test_queue_is_idempotent_and_off_when_disabled(self):
        self.assertIsNotNone(services.queue_event_post(self.event))
        services.queue_event_post(self.event)
        self.assertEqual(SocialPost.objects.count(), 1)
        with override_settings(INSTAGRAM_ENABLED=False):
            self.assertIsNone(services.queue_welcome_post(self.vendor))

    def test_dry_run_calls_nothing(self):
        post = services.queue_event_post(self.event)
        with override_settings(INSTAGRAM_DRY_RUN=True), mock.patch("social.instagram.requests.request") as req:
            msg = services.publish(post.pk)
        req.assert_not_called()
        self.assertIn("Dry run", msg)

    def test_publish_happy_path(self):
        post = services.queue_event_post(self.event)
        calls = []

        def fake(method, url, params=None, data=None, timeout=None):
            calls.append((method, url.rsplit("/", 2)[-2:]))
            body = {"id": "c1"}
            if "status_code" in (params or {}).get("fields", ""):
                body = {"status_code": "FINISHED"}
            elif url.endswith("media_publish"):
                body = {"id": "m1"}
            elif (params or {}).get("fields") == "permalink":
                body = {"permalink": "https://instagram.com/p/abc/"}
            return mock.Mock(status_code=200, json=lambda: body, text="")
        with mock.patch("social.instagram.requests.request", side_effect=fake) as req:
            self.assertEqual(services.publish(post.pk), "Posted to Instagram.")
        post.refresh_from_db()
        self.assertEqual((post.status, post.ig_media_id, post.permalink), ("posted", "m1", "https://instagram.com/p/abc/"))
        first = req.call_args_list[0]
        self.assertTrue(first.kwargs["data"]["image_url"].startswith("https://popupplug.com.ng/"))
        self.assertEqual(services.publish(post.pk), "Already posted or being posted.")  # no double post

    def test_api_error_marks_failed_and_can_retry(self):
        post = services.queue_event_post(self.event)
        resp = mock.Mock(status_code=400, json=lambda: {"error": {"message": "Bad token"}}, text="")
        with mock.patch("social.instagram.requests.request", return_value=resp):
            msg = services.publish(post.pk)
        post.refresh_from_db()
        self.assertEqual(post.status, "failed")
        self.assertIn("Bad token", msg)
        self.assertNotIn("SECRET123", post.note)

    def test_token_refresh_when_close_to_expiry(self):
        InstagramToken.objects.create(access_token="old", expires_at=timezone.now() + timedelta(days=10), refreshed_at=timezone.now() - timedelta(days=50))
        resp = mock.Mock(status_code=200, json=lambda: {"access_token": "new", "expires_in": 5184000}, text="")
        with mock.patch("social.instagram.requests.request", return_value=resp):
            token = instagram.refresh_if_needed(instagram.get_token())
        self.assertEqual(token.access_token, "new")
        self.assertGreater(instagram.token_days_left(), 50)

    def test_fresh_token_not_refreshed(self):
        InstagramToken.objects.create(access_token="old", expires_at=timezone.now() + timedelta(days=55), refreshed_at=timezone.now() - timedelta(days=5))
        with mock.patch("social.instagram.requests.request") as req:
            instagram.refresh_if_needed(instagram.get_token())
        req.assert_not_called()
