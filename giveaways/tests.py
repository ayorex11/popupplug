from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from events.models import Area, Category, Event
from events.tests import make_image
from vendors.models import Vendor

from .models import Entry, Giveaway, normalize_phone

User = get_user_model()
AJAX = {"HTTP_X_REQUESTED_WITH": "XMLHttpRequest"}


class PhoneTests(TestCase):
    def test_formats_collapse_to_one_number(self):
        for raw in ["08012345678", "0801 234 5678", "+234 801 234 5678", "2348012345678", "801-234-5678"]:
            self.assertEqual(normalize_phone(raw), "+2348012345678", raw)

    def test_rejects_junk(self):
        for raw in ["", "12345", "0601234567", "abc", "080123456789"]:
            self.assertIsNone(normalize_phone(raw), raw)


class GiveawayFlow(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("seed_lagos", verbosity=0)
        user = User.objects.create_user("v@example.com", "v@example.com", "pw-12345-xyz")
        vendor = Vendor.objects.create(user=user, name="Simmer & Sip", phone="08012345678", verified=True)
        cls.event = Event.objects.create(
            vendor=vendor, title="Juice Pop-Up", category=Category.objects.first(), area=Area.objects.first(),
            venue="The Hub", description="x", cover_image=make_image(size=(100, 100)),
            start_at=timezone.now() + timedelta(days=5), end_at=timezone.now() + timedelta(days=5, hours=4),
            status=Event.Status.PUBLISHED)
        cls.giveaway = Giveaway.objects.create(
            event=cls.event, prize="A ₦1,500 drink", winner_count=2, backup_count=2,
            closes_at=timezone.now() + timedelta(days=2))
        cls.staff = User.objects.create_user("boss@example.com", "boss@example.com", "pw-12345-xyz", is_staff=True)

    def setUp(self):
        cache.clear()
        self.url = reverse("giveaways:enter", args=[self.event.slug])

    def post(self, client=None, **over):
        data = {"name": "Ada Obi", "phone": "08012345678", "attend": "on", "rules": "on"}
        data.update(over)
        return (client or self.client).post(self.url, data, **AJAX)

    def test_enter_and_duplicates(self):
        r = self.post()
        self.assertTrue(r.json()["ok"])
        code = r.json()["code"]
        # same number, different format, fresh browser: same ticket, no second entry
        r2 = self.post(self.client_class(), phone="+234 801 234 5678", name="Someone Else")
        self.assertEqual(r2.json()["code"], code)
        self.assertEqual(Entry.objects.count(), 1)
        # same browser, different number: blocked by the session
        r3 = self.post(phone="09011111111")
        self.assertEqual(r3.json()["code"], code)
        self.assertEqual(Entry.objects.count(), 1)

    def test_validation_and_honeypot(self):
        self.assertEqual(self.post(phone="123").status_code, 400)
        self.assertEqual(self.post(attend="").status_code, 400)
        self.post(website="http://spam", phone="09022222222")
        self.assertEqual(Entry.objects.count(), 0)

    def test_closed_and_rate_limit(self):
        Giveaway.objects.filter(pk=self.giveaway.pk).update(closes_at=timezone.now() - timedelta(minutes=1))
        self.assertEqual(self.post().status_code, 400)
        Giveaway.objects.filter(pk=self.giveaway.pk).update(closes_at=timezone.now() + timedelta(days=1))
        for i in range(15):
            self.post(self.client_class(), phone=f"0801000{i:04d}")
        self.assertEqual(self.post(self.client_class(), phone="08099999999").status_code, 429)

    def test_event_page_shows_banner_and_no_pii(self):
        self.post()
        html = self.client.get(self.event.get_absolute_url()).content.decode()
        self.assertIn("Giveaway", html)
        self.assertNotIn("+2348012345678", html)

    def make_entries(self, n):
        for i in range(n):
            Entry.objects.create(giveaway=self.giveaway, name=f"Person {i}", phone=f"+23480100000{i:02d}")

    def test_draw_once_and_swap(self):
        self.make_entries(8)
        Entry.objects.filter(phone="+2348010000000").update(excluded=True)
        self.client.force_login(self.staff)
        act = reverse("desk:giveaway_action", args=[self.giveaway.pk])
        self.assertEqual(self.client.post(act, {"action": "draw"}).status_code, 302)
        self.assertFalse(Giveaway.objects.get(pk=self.giveaway.pk).drawn_at)  # still open: refused
        Giveaway.objects.filter(pk=self.giveaway.pk).update(closes_at=timezone.now() - timedelta(minutes=1))
        self.client.post(act, {"action": "draw"})
        e = Entry.objects
        self.assertEqual(e.filter(result="winner").count(), 2)
        self.assertEqual(e.filter(result="backup").count(), 2)
        self.assertEqual(e.get(phone="+2348010000000").result, "")  # excluded never picked
        winners_before = set(e.filter(result="winner").values_list("pk", flat=True))
        self.client.post(act, {"action": "draw"})  # second draw is a no-op
        self.assertEqual(set(e.filter(result="winner").values_list("pk", flat=True)), winners_before)
        # winner doesn't reply: backup 1 is promoted
        w = e.filter(result="winner").first()
        b1 = e.get(result="backup", backup_order=1)
        self.client.post(act, {"action": "declined", "entry": w.pk})
        w.refresh_from_db(); b1.refresh_from_db()
        self.assertEqual((w.result, b1.result), ("declined", "winner"))
        self.client.post(act, {"action": "claimed", "entry": b1.pk})
        b1.refresh_from_db()
        self.assertIsNotNone(b1.claimed_at)
        page = self.client.get(reverse("desk:giveaway"))
        self.assertContains(page, "wa.me/")

    def test_desk_is_staff_only(self):
        self.assertEqual(self.client.get(reverse("desk:giveaway")).status_code, 302)
        self.client.force_login(User.objects.create_user("x@example.com", "x@example.com", "pw-12345-xyz"))
        self.assertEqual(self.client.get(reverse("desk:giveaway")).status_code, 302)


class CardBadge(GiveawayFlow):
    def test_badge_on_home_and_list_only_while_open(self):
        for name in ("events:home", "events:list"):
            cache.clear()
            self.assertContains(self.client.get(reverse(name)), "Giveaway: 2 winners")
        Giveaway.objects.filter(pk=self.giveaway.pk).update(closes_at=timezone.now() - timedelta(minutes=1))
        cache.clear()
        self.assertNotContains(self.client.get(reverse("events:list")), "Giveaway: 2 winners")
