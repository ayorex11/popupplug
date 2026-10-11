from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from .models import Vendor

User = get_user_model()

VALID = {
    "email": "new@example.com",
    "password1": "a-Strong-pass-123", "password2": "a-Strong-pass-123",
    "name": "Fresh Bakes", "phone": "0803 123 4567", "instagram": "@freshbakes", "twitter": "",
}


class SignupTests(TestCase):
    def test_signup_creates_user_and_vendor_and_logs_in(self):
        r = self.client.post(reverse("vendors:signup"), VALID)
        self.assertRedirects(r, reverse("vendors:dashboard"))
        v = Vendor.objects.get(name="Fresh Bakes")
        self.assertEqual(v.phone, "08031234567")      # spaces stripped
        self.assertEqual(v.instagram, "freshbakes")   # @ stripped
        self.assertFalse(v.verified)
        self.assertEqual(v.slug, "fresh-bakes")

    def test_rejects_bad_phone(self):
        r = self.client.post(reverse("vendors:signup"), {**VALID, "phone": "12345"})
        self.assertIn("phone", r.context["form"].errors)
        self.assertFalse(Vendor.objects.exists())

    def test_rejects_duplicate_email(self):
        User.objects.create_user("x", "new@example.com", "pw-12345-xyz")
        r = self.client.post(reverse("vendors:signup"), VALID)
        self.assertIn("email", r.context["form"].errors)

    def test_vendor_slugs_are_unique(self):
        for i in range(2):
            u = User.objects.create_user(f"u{i}", f"u{i}@example.com", "pw-12345-xyz")
            Vendor.objects.create(user=u, name="Same Name", phone="08011111111")
        self.assertEqual(set(Vendor.objects.values_list("slug", flat=True)), {"same-name", "same-name-2"})

    def test_dashboard_requires_login(self):
        r = self.client.get(reverse("vendors:dashboard"))
        self.assertEqual(r.status_code, 302)

    def test_public_profile_renders(self):
        u = User.objects.create_user("p", "p@example.com", "pw-12345-xyz")
        v = Vendor.objects.create(user=u, name="Profile Co", phone="08011111111")
        self.assertContains(self.client.get(reverse("vendors:profile", args=[v.slug])), "Profile Co")
