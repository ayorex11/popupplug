from datetime import timedelta

from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone

from vendors.forms import VendorSignupForm
from vendors.models import Vendor

from .models import Category, Event
from .tests import Base

User = get_user_model()


class OrganiserSignupTests(Base):
    def signup(self, **kw):
        data = {"role": "organiser", "name": "Lagos Markets", "email": "org@example.com",
                "password1": "pw-12345-xyz", "password2": "pw-12345-xyz"}
        data.update(kw)
        return VendorSignupForm(data)

    def test_social_required_even_with_phone(self):
        for role in ("vendor", "organiser", "both"):
            f = self.signup(role=role, phone="08012345678")
            self.assertFalse(f.is_valid(), role)
            self.assertIn("instagram", f.errors)

    def test_organiser_needs_one_contact(self):
        self.assertFalse(self.signup().is_valid())

    def test_organiser_with_tiktok_only(self):
        f = self.signup(tiktok="https://www.tiktok.com/@lagosmarkets")
        self.assertTrue(f.is_valid(), f.errors)
        self.assertEqual(f.cleaned_data["tiktok"], "lagosmarkets")

    def test_vendor_needs_phone(self):
        self.assertFalse(self.signup(role="vendor", instagram="x").is_valid())

    def test_role_defaults_to_vendor(self):
        f = self.signup(role="", phone="08012345678", twitter="bob")
        self.assertTrue(f.is_valid(), f.errors)
        self.assertEqual(f.cleaned_data["role"], "vendor")

    def test_signup_page_renders(self):
        self.assertContains(self.client.get(reverse("vendors:signup")), "organise")


class VendorCallFormTests(Base):
    def setUp(self):
        self.vendor.role = "organiser"
        self.vendor.save()
        self.client.force_login(self.user)

    def post(self, **kw):
        return self.client.post(reverse("events:create"), self.form_data(**kw))

    def test_price_set(self):
        r = self.post(seeking_vendors="on", booth_price="15000")
        self.assertEqual(r.status_code, 302)
        e = Event.objects.get(title="Lekki Cake Day")
        self.assertEqual(e.booth_price, 15000)
        self.assertTrue(e.seeking_vendors)

    def test_contact_for_price(self):
        self.post(seeking_vendors="on", booth_price_on_request="on")
        e = Event.objects.get(title="Lekki Cake Day")
        self.assertTrue(e.booth_price_on_request)
        self.assertIsNone(e.booth_price)

    def test_price_and_ask_conflict(self):
        r = self.post(seeking_vendors="on", booth_price="1000", booth_price_on_request="on")
        self.assertEqual(r.status_code, 200)
        self.assertFalse(Event.objects.filter(title="Lekki Cake Day").exists())

    def test_neither_price_nor_ask(self):
        self.assertEqual(self.post(seeking_vendors="on").status_code, 200)

    def test_max_below_min(self):
        r = self.post(seeking_vendors="on", booth_price="20000", booth_price_max="10000")
        self.assertEqual(r.status_code, 200)

    def test_call_data_cleared_when_not_seeking(self):
        self.post(booth_price="5000")
        e = Event.objects.get(title="Lekki Cake Day")
        self.assertFalse(e.seeking_vendors)
        self.assertIsNone(e.booth_price)

    def test_all_categories_only_for_organisers(self):
        general = Category.objects.get(is_general=True)
        self.assertEqual(self.post(category=general.pk, seeking_vendors="on", booth_price="1").status_code, 302)
        self.assertNotContains(self.client.get(reverse("events:list")), ">All categories</a>")
        self.vendor.role = "vendor"
        self.vendor.save()
        r = self.post(title="Vendor Try", category=general.pk)
        self.assertEqual(r.status_code, 200)
        self.assertIn("category", r.context["form"].errors)

    def test_plain_vendor_has_no_call_fields(self):
        self.vendor.role = "vendor"
        self.vendor.save()
        self.assertNotContains(self.client.get(reverse("events:create")), "id_seeking_vendors")


class VendorCallsPageTests(Base):
    def setUp(self):
        self.lekki = self.make_event(title="Lekki Market", seeking_vendors=True, booth_price=10000)
        self.ask = self.make_event(title="Ask Market", seeking_vendors=True, booth_price_on_request=True)
        self.free = self.make_event(title="Free Booth Fair", seeking_vendors=True, booth_price=0)
        self.closed = self.make_event(title="Closed Fair", seeking_vendors=True, booth_price=1, vendor_call_closed=True)
        self.expired = self.make_event(title="Expired Call", seeking_vendors=True, booth_price=1,
                                       apply_by=timezone.localdate() - timedelta(days=1))
        self.draft = self.make_event(title="Draft Fair", seeking_vendors=True, booth_price=1, status=Event.Status.PENDING)
        self.plain = self.make_event(title="Plain Pop-up")
        self.url = reverse("events:vendor_calls")

    def titles(self, resp):
        return {e.title for e in resp.context["page"]}

    def test_lists_only_open_calls(self):
        t = self.titles(self.client.get(self.url))
        self.assertEqual(t, {"Lekki Market", "Ask Market", "Free Booth Fair"})

    def test_budget_hides_ask_by_default(self):
        r = self.client.get(self.url, {"budget": 10000})
        self.assertEqual(self.titles(r), {"Lekki Market", "Free Booth Fair"})
        self.assertEqual(r.context["hidden_ask"], 1)

    def test_budget_with_ask(self):
        r = self.client.get(self.url, {"budget": 10000, "ask": 1})
        self.assertIn("Ask Market", self.titles(r))

    def test_free_budget(self):
        self.assertEqual(self.titles(self.client.get(self.url, {"budget": 0})), {"Free Booth Fair"})

    def test_area_filter(self):
        other = self.make_event(title="Ikeja Fair", seeking_vendors=True, booth_price=500,
                                area=self.area.__class__.objects.exclude(pk=self.area.pk).first())
        r = self.client.get(self.url, {"area": other.area.slug})
        self.assertEqual(self.titles(r), {"Ikeja Fair"})

    def test_general_category_matches_every_category_filter(self):
        from .models import Category
        general = Category.objects.get(is_general=True)
        self.make_event(title="Any Vendor Market", seeking_vendors=True, booth_price=1, category=general)
        other = Category.objects.filter(is_general=False).exclude(pk=self.category.pk).first()
        titles = self.titles(self.client.get(self.url, {"category": other.slug}))
        self.assertIn("Any Vendor Market", titles)
        self.assertNotIn("Lekki Market", titles)
        self.assertContains(self.client.get(reverse("events:list"), {"category": other.slug}), "Any Vendor Market")

    def test_badge_on_cards_and_detail(self):
        self.assertContains(self.client.get(reverse("events:list")), "Vendors wanted")
        d = self.client.get(self.lekki.get_absolute_url())
        self.assertContains(d, "booth payments")
        self.assertContains(d, "10,000")
        self.assertNotContains(self.client.get(self.plain.get_absolute_url()), "booth payments")

    def test_sitemap_has_calls(self):
        self.assertContains(self.client.get("/sitemap.xml"), "/vendor-calls/")


class ProfileRoleTests(Base):
    def test_switch_role_and_blank_phone(self):
        self.client.force_login(self.user)
        r = self.client.post(reverse("vendors:edit_profile"), {
            "role": "organiser", "name": "Sweet Tooth", "bio": "", "phone": "",
            "instagram": "sweettooth", "tiktok": "", "twitter": "", "website": "sweettooth.ng"})
        self.assertEqual(r.status_code, 302)
        self.vendor.refresh_from_db()
        self.assertEqual(self.vendor.role, "organiser")
        self.assertEqual(self.vendor.website, "https://sweettooth.ng")
        self.assertEqual(self.vendor.whatsapp_url, "")
        self.assertContains(self.client.get(reverse("vendors:profile", args=[self.vendor.slug])), "Organiser")


from django.core import mail
from django.test import override_settings


@override_settings(NOTIFY_ASYNC=False, ADMIN_NOTIFY_EMAILS=["admin@example.com"])
class ReapprovalTests(Base):
    def setUp(self):
        self.vendor.verified = True
        self.vendor.instagram = "sweettooth"
        self.vendor.save()
        self.client.force_login(self.user)

    def test_verified_vendor_event_edit_goes_back_to_pending(self):
        e = self.make_event()
        with self.captureOnCommitCallbacks(execute=True):
            r = self.client.post(reverse("events:edit", args=[e.slug]), self.form_data(title="Changed Title"))
        self.assertEqual(r.status_code, 302)
        e.refresh_from_db()
        self.assertEqual(e.status, Event.Status.PENDING)
        self.assertEqual(self.client.get(e.get_absolute_url()).status_code, 200)  # owner still sees it
        self.client.logout()
        self.assertEqual(self.client.get(e.get_absolute_url()).status_code, 404)
        self.assertTrue(any("Edited event to approve" in m.subject for m in mail.outbox))

    def test_unchanged_event_save_keeps_status(self):
        data = self.form_data()
        self.client.post(reverse("events:create"), data)
        e = Event.objects.get(title="Lekki Cake Day")
        self.assertEqual(e.status, Event.Status.PUBLISHED)  # verified vendor, new event
        data.pop("cover_image")
        self.client.post(reverse("events:edit", args=[e.slug]), data)
        e.refresh_from_db()
        self.assertEqual(e.status, Event.Status.PUBLISHED)

    def test_profile_edit_unverifies_and_notifies(self):
        data = {"role": "vendor", "name": "Sweet Tooth Bakes", "bio": "", "phone": "08012345678",
                "instagram": "newhandle", "tiktok": "", "twitter": "", "website": ""}
        with self.captureOnCommitCallbacks(execute=True):
            self.client.post(reverse("vendors:edit_profile"), data)
        self.vendor.refresh_from_db()
        self.assertFalse(self.vendor.verified)
        self.assertTrue(any("re-approve" in m.subject for m in mail.outbox))

    def test_profile_save_without_changes_keeps_verified(self):
        data = {"role": "vendor", "name": "Sweet Tooth Bakes", "bio": "", "phone": "08012345678",
                "instagram": "sweettooth", "tiktok": "", "twitter": "", "website": ""}
        self.client.post(reverse("vendors:edit_profile"), data)
        self.vendor.refresh_from_db()
        self.assertTrue(self.vendor.verified)


@override_settings(NOTIFY_ASYNC=False, SITE_URL="https://popupplug.com.ng")
class PasswordResetTests(Base):
    def test_link_on_login_page(self):
        self.assertContains(self.client.get("/login/"), "Forgot your password?")

    def test_full_flow(self):
        with self.captureOnCommitCallbacks(execute=True):
            r = self.client.post("/password-reset/", {"email": "BAKER@example.com"})
        self.assertRedirects(r, "/password-reset/sent/")
        self.assertEqual(len(mail.outbox), 1)
        body = mail.outbox[0].body
        link = next(w for w in body.split() if "/reset/" in w)
        self.assertTrue(link.startswith("https://popupplug.com.ng/reset/"))
        r = self.client.get(link.replace("https://popupplug.com.ng", ""), follow=True)
        r = self.client.post(r.redirect_chain[-1][0], {"new_password1": "Brand-new-pw-987", "new_password2": "Brand-new-pw-987"})
        self.assertRedirects(r, "/reset/done/")
        self.assertTrue(self.client.login(username="baker", password="Brand-new-pw-987"))

    def test_unknown_email_looks_identical_and_sends_nothing(self):
        with self.captureOnCommitCallbacks(execute=True):
            r = self.client.post("/password-reset/", {"email": "nobody@example.com"})
        self.assertRedirects(r, "/password-reset/sent/")
        self.assertEqual(len(mail.outbox), 0)

    def test_throttled_per_account(self):
        from django.core.cache import cache
        cache.clear()
        with self.captureOnCommitCallbacks(execute=True):
            self.client.post("/password-reset/", {"email": "baker@example.com"})
            self.client.post("/password-reset/", {"email": "baker@example.com"})
        self.assertEqual(len(mail.outbox), 1)

    def test_reset_pages_noindex(self):
        self.assertIn("noindex", self.client.get("/password-reset/")["X-Robots-Tag"])


@override_settings(NOTIFY_ASYNC=False, ADMIN_NOTIFY_EMAILS=["admin@example.com"])
class ChangeTrackingTests(Base):
    def setUp(self):
        self.vendor.verified = True
        self.vendor.instagram = "sweettooth"
        self.vendor.role = "organiser"
        self.vendor.save()
        self.client.force_login(self.user)
        self.staff = User.objects.create_user("boss", "boss@example.com", "pw-12345-xyz", is_staff=True)

    def profile(self, **kw):
        d = {"role": "organiser", "name": "Sweet Tooth Bakes", "bio": "", "phone": "08012345678",
             "instagram": "sweettooth", "tiktok": "", "twitter": "", "website": ""}
        d.update(kw)
        return d

    def test_profile_changes_recorded_merged_and_shown_in_desk(self):
        with self.captureOnCommitCallbacks(execute=True):
            self.client.post(reverse("vendors:edit_profile"), self.profile(instagram="newhandle"))
        self.vendor.refresh_from_db()
        self.assertEqual(self.vendor.pending_changes["Instagram"], {"old": "sweettooth", "new": "newhandle"})
        self.client.post(reverse("vendors:edit_profile"), self.profile(instagram="third", tiktok="tt"))
        self.vendor.refresh_from_db()
        self.assertEqual(self.vendor.pending_changes["Instagram"], {"old": "sweettooth", "new": "third"})
        self.assertIn("TikTok", self.vendor.pending_changes)
        self.assertTrue(any("sweettooth" in m.body and "newhandle" in m.body for m in mail.outbox))
        self.client.force_login(self.staff)
        page = self.client.get(reverse("desk:vendors") + "?tab=pending")
        self.assertContains(page, "Changed since last approval")
        self.assertContains(page, "third")
        self.assertContains(page, "Approve changes")

    def test_approval_clears_changes(self):
        self.client.post(reverse("vendors:edit_profile"), self.profile(instagram="newhandle"))
        self.client.force_login(self.staff)
        self.client.post(reverse("desk:vendor_action", args=[self.vendor.pk]), {"action": "approve"})
        self.vendor.refresh_from_db()
        self.assertTrue(self.vendor.verified)
        self.assertEqual(self.vendor.pending_changes, {})

    def test_event_edit_records_changes(self):
        e = self.make_event()
        self.client.post(reverse("events:edit", args=[e.slug]), self.form_data(title="Brand New Title"))
        e.refresh_from_db()
        self.assertEqual(e.pending_changes["Title"], {"old": "Cake Pop-Up", "new": "Brand New Title"})
        self.client.force_login(self.staff)
        self.assertContains(self.client.get(reverse("desk:events") + "?tab=pending"), "Brand New Title")
        self.client.post(reverse("desk:event_action", args=[e.pk]), {"action": "approve"})
        e.refresh_from_db()
        self.assertEqual(e.pending_changes, {})

    def test_closing_applications_needs_no_reapproval(self):
        data = self.form_data(seeking_vendors="on", booth_price="5000")
        self.client.post(reverse("events:create"), data)
        e = Event.objects.get(title="Lekki Cake Day")
        self.assertEqual(e.status, Event.Status.PUBLISHED)
        data.pop("cover_image")
        self.client.post(reverse("events:edit", args=[e.slug]), {**data, "vendor_call_closed": "on"})
        e.refresh_from_db()
        self.assertTrue(e.vendor_call_closed)
        self.assertEqual(e.status, Event.Status.PUBLISHED)
        self.assertEqual(e.pending_changes, {})
