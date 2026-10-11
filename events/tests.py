import io
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.db import connection
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone
from PIL import Image

from vendors.models import Vendor

from .models import Area, Category, Event, Interested
from .views import weekend_window

User = get_user_model()


def make_image(fmt="PNG", size=(2400, 1800), name="poster.png"):
    buf = io.BytesIO()
    Image.new("RGB", size, (200, 80, 40)).save(buf, format=fmt)
    return SimpleUploadedFile(name, buf.getvalue(), content_type=f"image/{fmt.lower()}")


class Base(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_lagos", verbosity=0)
        cls.area = Area.objects.get(slug="lekki")
        cls.category = Category.objects.get(slug="cakes-pastries")
        cls.user = User.objects.create_user("baker", "baker@example.com", "pw-12345-xyz")
        cls.vendor = Vendor.objects.create(user=cls.user, name="Sweet Tooth Bakes", phone="08012345678")

    def make_event(self, **kw):
        start = kw.pop("start_at", timezone.now() + timedelta(days=2))
        defaults = dict(
            vendor=self.vendor, title="Cake Pop-Up", category=self.category, area=self.area,
            venue="The Hub, Admiralty Way", description="Cakes!", cover_image="events/x.webp",
            start_at=start, end_at=start + timedelta(hours=6), status=Event.Status.PUBLISHED,
        )
        defaults.update(kw)
        return Event.objects.create(**defaults)

    def form_data(self, **kw):
        start = timezone.localtime(timezone.now() + timedelta(days=3)).replace(second=0, microsecond=0)
        data = {
            "title": "Lekki Cake Day", "category": self.category.pk, "area": self.area.pk,
            "venue": "12 Admiralty Way", "description": "Fresh cakes all day.",
            "start_at": start.strftime("%Y-%m-%dT%H:%M"),
            "end_at": (start + timedelta(hours=5)).strftime("%Y-%m-%dT%H:%M"),
            "is_free_entry": "on", "entry_note": "",
            "cover_image": make_image(),
        }
        data.update(kw)
        return data


class PublicPageTests(Base):
    def test_home_and_list_render(self):
        self.make_event()
        self.assertContains(self.client.get(reverse("events:home")), "Cake Pop-Up")
        self.assertContains(self.client.get(reverse("events:list")), "Cake Pop-Up")

    def test_pending_events_hidden_from_public(self):
        e = self.make_event(status=Event.Status.PENDING, title="Secret Pending")
        self.assertNotContains(self.client.get(reverse("events:list")), "Secret Pending")
        self.assertEqual(self.client.get(e.get_absolute_url()).status_code, 404)

    def test_owner_can_view_pending(self):
        e = self.make_event(status=Event.Status.PENDING)
        self.client.login(username="baker", password="pw-12345-xyz")
        self.assertEqual(self.client.get(e.get_absolute_url()).status_code, 200)

    def test_filters(self):
        yaba = Area.objects.get(slug="yaba")
        self.make_event(title="Lekki One")
        self.make_event(title="Yaba One", area=yaba)
        r = self.client.get(reverse("events:list"), {"area": "yaba"})
        self.assertContains(r, "Yaba One")
        self.assertNotContains(r, "Lekki One")
        r = self.client.get(reverse("events:list"), {"q": "Lekki"})
        self.assertContains(r, "Lekki One")
        self.assertNotContains(r, "Yaba One")

    def test_detail_has_open_graph_tags(self):
        e = self.make_event()
        html = self.client.get(e.get_absolute_url()).content.decode()
        self.assertIn('property="og:title" content="Cake Pop-Up"', html)
        self.assertIn('property="og:image"', html)
        self.assertIn('property="og:url"', html)

    def test_past_events_excluded_from_upcoming(self):
        self.make_event(title="Old News", start_at=timezone.now() - timedelta(days=5))
        self.assertNotContains(self.client.get(reverse("events:list")), "Old News")
        self.assertContains(self.client.get(reverse("events:list"), {"when": "past"}), "Old News")

    def test_weekend_window_is_fri_to_sun(self):
        wed = timezone.make_aware(timezone.datetime(2026, 10, 7, 12, 0))  # Wednesday
        start, end = weekend_window(wed)
        self.assertEqual((start.weekday(), start.hour), (4, 0))
        self.assertEqual(end.weekday(), 6)
        sat = timezone.make_aware(timezone.datetime(2026, 10, 10, 15, 0))  # Saturday
        start, _ = weekend_window(sat)
        self.assertEqual(start, sat)


class CachingTests(Base):
    @override_settings(PUBLIC_PAGE_CACHE_SECONDS=60)
    def test_cached_for_anonymous_and_invalidated_on_change(self):
        self.make_event(title="First Event")
        url = reverse("events:list")
        self.assertContains(self.client.get(url), "First Event")
        with self.assertNumQueries(0):
            self.client.get(url)  # served from cache
        self.make_event(title="Second Event")  # post_save bumps the cache version
        self.assertContains(self.client.get(url), "Second Event")

    @override_settings(PUBLIC_PAGE_CACHE_SECONDS=60)
    def test_logged_in_users_bypass_cache(self):
        self.make_event()
        url = reverse("events:list")
        self.client.get(url)  # warm the cache as an anonymous visitor
        self.client.login(username="baker", password="pw-12345-xyz")
        with CaptureQueriesContext(connection) as ctx:
            r = self.client.get(url)
        self.assertGreater(len(ctx), 0)  # rendered fresh, not served from cache
        self.assertContains(r, "My events")  # logged-in nav, never the cached anonymous page


class PostingTests(Base):
    def setUp(self):
        self.client.login(username="baker", password="pw-12345-xyz")

    def test_login_required(self):
        self.client.logout()
        r = self.client.get(reverse("events:create"))
        self.assertEqual(r.status_code, 302)
        self.assertIn("/login/", r["Location"])

    def test_unverified_vendor_event_is_pending_and_image_is_compressed(self):
        r = self.client.post(reverse("events:create"), self.form_data())
        self.assertEqual(r.status_code, 302)
        e = Event.objects.get(title="Lekki Cake Day")
        self.assertEqual(e.status, Event.Status.PENDING)
        self.assertTrue(e.cover_image.name.endswith(".webp"))
        with Image.open(e.cover_image.path) as img:
            self.assertEqual(img.format, "WEBP")
            self.assertLessEqual(max(img.size), 1280)
        e.cover_image.delete(save=False)

    def test_verified_vendor_publishes_instantly(self):
        Vendor.objects.filter(pk=self.vendor.pk).update(verified=True)
        self.client.post(reverse("events:create"), self.form_data())
        e = Event.objects.get(title="Lekki Cake Day")
        self.assertEqual(e.status, Event.Status.PUBLISHED)
        e.cover_image.delete(save=False)

    def test_rejects_non_image_upload(self):
        bad = SimpleUploadedFile("evil.png", b"<?php echo 'hi'; ?>", content_type="image/png")
        r = self.client.post(reverse("events:create"), self.form_data(cover_image=bad))
        self.assertEqual(r.status_code, 200)
        self.assertIn("cover_image", r.context["form"].errors)
        self.assertFalse(Event.objects.filter(title="Lekki Cake Day").exists())

    def test_rejects_end_before_start(self):
        data = self.form_data()
        data["end_at"] = data["start_at"]
        r = self.client.post(reverse("events:create"), data)
        self.assertIn("end_at", r.context["form"].errors)

    def test_rejects_past_start(self):
        past = (timezone.localtime(timezone.now()) - timedelta(days=2)).strftime("%Y-%m-%dT%H:%M")
        r = self.client.post(reverse("events:create"), self.form_data(start_at=past))
        self.assertIn("start_at", r.context["form"].errors)

    @override_settings(MAX_EVENTS_PER_DAY=2)
    def test_daily_post_limit(self):
        self.make_event(title="One")
        self.make_event(title="Two")
        r = self.client.post(reverse("events:create"), self.form_data())
        self.assertEqual(r.status_code, 200)
        self.assertIn("per day", str(r.context["form"].non_field_errors()))

    def test_cannot_edit_or_delete_another_vendors_event(self):
        other_user = User.objects.create_user("other", "o@example.com", "pw-12345-xyz")
        other = Vendor.objects.create(user=other_user, name="Other Co", phone="08098765432")
        e = self.make_event(vendor=other, title="Not Mine")
        self.assertEqual(self.client.get(reverse("events:edit", args=[e.slug])).status_code, 404)
        self.assertEqual(self.client.post(reverse("events:delete", args=[e.slug])).status_code, 404)
        self.assertTrue(Event.objects.filter(pk=e.pk).exists())

    def test_edit_by_unverified_vendor_returns_to_pending(self):
        e = self.make_event()
        data = self.form_data(title="Edited Title")
        data["cover_image"] = ""  # keep existing image
        data.pop("cover_image")
        e.cover_image = "events/x.webp"
        e.save()
        self.client.post(reverse("events:edit", args=[e.slug]), data)
        e.refresh_from_db()
        self.assertEqual(e.title, "Edited Title")
        self.assertEqual(e.status, Event.Status.PENDING)


class InterestedTests(Base):
    def test_anonymous_toggle_counts_once_and_toggles_off(self):
        e = self.make_event()
        url = reverse("events:interested", args=[e.slug])
        r = self.client.post(url, HTTP_X_REQUESTED_WITH="XMLHttpRequest")
        self.assertEqual(r.json(), {"interested": True, "count": 1})
        r = self.client.post(url, HTTP_X_REQUESTED_WITH="XMLHttpRequest")
        self.assertEqual(r.json(), {"interested": False, "count": 0})
        self.assertEqual(Interested.objects.count(), 0)

    def test_two_visitors_count_separately(self):
        from django.test import Client
        e = self.make_event()
        url = reverse("events:interested", args=[e.slug])
        Client().post(url)
        Client().post(url)
        e.refresh_from_db()
        self.assertEqual(e.interested_count, 2)

    def test_get_not_allowed(self):
        e = self.make_event()
        self.assertEqual(self.client.get(reverse("events:interested", args=[e.slug])).status_code, 405)

    def test_cannot_mark_pending_event(self):
        e = self.make_event(status=Event.Status.PENDING)
        self.assertEqual(self.client.post(reverse("events:interested", args=[e.slug])).status_code, 404)