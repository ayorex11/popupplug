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

class NotificationTests(TestCase):
    def test_login_required_explains_redirect(self):
        r = self.client.get("/vendors/dashboard/", follow=True)
        self.assertContains(r, "Please log in to continue.")
        self.assertContains(r, 'class="toast warning"')

    def test_login_and_logout_toast(self):
        from django.contrib.auth import get_user_model
        get_user_model().objects.create_user("a@b.com", "a@b.com", "pw-12345-x")
        r = self.client.post("/login/", {"username": "a@b.com", "password": "pw-12345-x"}, follow=True)
        self.assertContains(r, "You&#x27;re logged in.")
        r = self.client.post("/logout/", follow=True)
        self.assertContains(r, "logged out")

    def test_no_native_dialogs_in_templates(self):
        import pathlib
        for f in pathlib.Path("templates").rglob("*.html"):
            t = f.read_text()
            self.assertNotIn("confirm(", t, f)
            self.assertNotIn("alert(", t, f)


class SeoTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        from datetime import timedelta
        from django.utils import timezone
        from events.models import Area, Category, Event
        from vendors.models import Vendor
        call_command("seed_lagos", verbosity=0)
        u = User.objects.create_user("v", "v@example.com", "pw-12345-xyz")
        cls.vendor = Vendor.objects.create(user=u, name="Ada <Bakes> & Co", phone="08012345678")
        kw = dict(vendor=cls.vendor, category=Category.objects.first(), area=Area.objects.get(slug="lekki"),
                  venue="The Hub, Admiralty Way", description="Cakes </script> galore", cover_image="events/x.webp")
        start = timezone.now() + timedelta(days=3)
        cls.live = Event.objects.create(title="Live Cake Day", start_at=start, end_at=start + timedelta(hours=5), status="published", **kw)
        cls.pending = Event.objects.create(title="Secret Pending", start_at=start, end_at=start + timedelta(hours=5), status="pending", **kw)

    def test_robots(self):
        r = self.client.get("/robots.txt")
        self.assertEqual(r["Content-Type"].split(";")[0], "text/plain")
        self.assertContains(r, "Disallow: /desk/")
        self.assertContains(r, "Sitemap: ")
        self.assertContains(r, "/sitemap.xml")

    def test_sitemap_lists_only_published(self):
        r = self.client.get("/sitemap.xml")
        self.assertEqual(r["Content-Type"].split(";")[0], "application/xml")
        body = r.content.decode()
        self.assertIn(self.live.get_absolute_url(), body)
        self.assertNotIn(self.pending.slug, body)
        self.assertIn(f"/vendors/{self.vendor.slug}/", body)
        self.assertNotIn("/desk/", body)
        import xml.dom.minidom
        xml.dom.minidom.parseString(r.content)  # well-formed

    def test_event_page_has_canonical_and_valid_jsonld(self):
        import json, re
        r = self.client.get(self.live.get_absolute_url() + "?utm_source=x")
        html = r.content.decode()
        self.assertIn(f'<link rel="canonical" href="http://localhost:8000{self.live.get_absolute_url()}">', html)
        m = re.search(r'<script type="application/ld\+json">(.*?)</script>', html, re.S)
        data = json.loads(m.group(1))
        self.assertEqual(data["@type"], "Event")
        self.assertEqual(data["location"]["address"]["addressCountry"], "NG")
        self.assertTrue(data["isAccessibleForFree"])
        self.assertNotIn("</script>", m.group(1))  # description with </script> must be escaped

    def test_unpublished_event_not_indexable(self):
        self.client.force_login(self.vendor.user)
        r = self.client.get(self.pending.get_absolute_url())
        self.assertContains(r, 'content="noindex, nofollow"')
        self.assertNotContains(r, "application/ld+json")

    def test_home_has_site_schema_and_og(self):
        r = self.client.get("/")
        self.assertContains(r, '"@type": "WebSite"')
        self.assertContains(r, "og-default")
        self.assertContains(r, 'rel="canonical"')

    def test_search_results_noindex_but_list_canonical_is_clean(self):
        r = self.client.get("/events/?q=cake&area=lekki")
        self.assertContains(r, 'content="noindex, follow"')
        self.assertContains(r, 'rel="canonical" href="http://localhost:8000/events/"')
        r = self.client.get("/events/?area=lekki")
        self.assertContains(r, 'content="index, follow')

    def test_private_pages_send_noindex_header(self):
        for path in ("/login/", "/desk/", "/vendors/dashboard/", "/events/new/"):
            r = self.client.get(path)
            self.assertEqual(r.get("X-Robots-Tag"), "noindex, nofollow", path)
