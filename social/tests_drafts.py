from datetime import timedelta

from django.test import override_settings
from django.urls import reverse
from django.utils import timezone

from events.tests import Base

from . import cards
from .models import SocialPost


class DraftTests(Base):
    def test_tiktok_caption_has_at_most_five_hashtags(self):
        c = cards.tiktok_event_caption(self.make_event())
        self.assertLessEqual(cards.hashtag_count(c), 5)
        self.assertGreaterEqual(cards.hashtag_count(c), 1)
        self.assertIn("Cake Pop-Up", c)

    def test_limit_hashtags_trims_extras(self):
        out = cards.limit_hashtags("Hi #a #b #c #d #e #f #g there")
        self.assertEqual(cards.hashtag_count(out), 5)
        self.assertTrue(out.startswith("Hi #a"))

    def test_x_post_fits_and_keeps_link_even_with_long_title(self):
        e = self.make_event(title="A" * 139, venue="V" * 100)
        post = cards.x_event_post(e)
        self.assertLessEqual(len(post), 250)
        self.assertIn(e.slug, post)
        self.assertIn("Lekki", post)

    def test_x_post_short_event_gets_extras(self):
        self.vendor.twitter = "sweettooth"
        self.vendor.save()
        post = cards.x_event_post(self.make_event())
        self.assertLessEqual(len(post), 250)
        self.assertIn("@sweettooth", post)
        self.assertIn("#LagosPopUp", post)

    def test_multi_day_event_wording(self):
        start = timezone.now() + timedelta(days=3)
        e = self.make_event(start_at=start, end_at=start + timedelta(days=2))
        self.assertIn(" to ", cards.x_event_post(e))

    def test_welcome_drafts(self):
        self.assertLessEqual(len(cards.x_welcome_post(self.vendor)), 250)
        self.assertLessEqual(cards.hashtag_count(cards.tiktok_welcome_caption(self.vendor)), 5)

    def test_desk_shows_drafts(self):
        from django.contrib.auth import get_user_model
        staff = get_user_model().objects.create_user("boss", "b@example.com", "pw-12345-xyz", is_staff=True)
        e = self.make_event()
        SocialPost.objects.create(kind="event", event=e, vendor=self.vendor, caption="c", image="social/x.jpg")
        self.client.force_login(staff)
        page = self.client.get(reverse("desk:social"))
        self.assertContains(page, "TikTok caption")
        self.assertContains(page, "X post")
        self.assertContains(page, "Cake Pop-Up")


class WelcomeRoleTests(Base):
    def test_wording_follows_role(self):
        for role, needle in (("vendor", "Follow along for their pop-ups in Lagos"),
                             ("organiser", "events are now listed"),
                             ("both", "pop-ups and events")):
            self.vendor.role = role
            self.assertIn(needle, cards.welcome_caption(self.vendor), role)
            self.assertLessEqual(len(cards.x_welcome_post(self.vendor)), 250)
            self.assertLessEqual(cards.hashtag_count(cards.tiktok_welcome_caption(self.vendor)), 5)

    def test_cards_render_for_every_role(self):
        for role in ("vendor", "organiser", "both"):
            self.vendor.role = role
            self.assertTrue(cards.render_welcome_card(self.vendor))
