import re

from django.conf import settings
from django.db import models
from django.utils.text import slugify


def normalize_ng_phone(phone):
    """Return a Nigerian number as 234XXXXXXXXXX (digits only), whatever format it was typed in."""
    digits = re.sub(r"\D", "", phone or "")
    if digits.startswith("234"):
        return digits
    if digits.startswith("0"):
        return "234" + digits[1:]
    return "234" + digits


class Vendor(models.Model):
    """A business, individual or event organiser who posts pop-up events.

    Organisers are profiles too: one account, one approval flow, one set of contact fields.
    `role` says whether the profile sells at pop-ups, organises them, or both.
    """

    class Role(models.TextChoices):
        VENDOR = "vendor", "Vendor"
        ORGANISER = "organiser", "Organiser"
        BOTH = "both", "Vendor and organiser"

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="vendor")
    role = models.CharField(max_length=10, choices=Role.choices, default=Role.VENDOR, db_index=True)
    name = models.CharField("Business / brand name", max_length=120)
    slug = models.SlugField(max_length=140, unique=True, blank=True)
    bio = models.CharField(max_length=300, blank=True)
    phone = models.CharField(max_length=20, blank=True, help_text="WhatsApp-able number, e.g. 08012345678. Required for vendors; optional for organisers.")
    instagram = models.CharField(max_length=60, blank=True, help_text="Handle without the @")
    tiktok = models.CharField("TikTok", max_length=60, blank=True, help_text="Handle without the @")
    twitter = models.CharField("Twitter/X", max_length=60, blank=True, help_text="Handle without the @")
    website = models.URLField(max_length=200, blank=True)
    # Verified vendors publish instantly; everyone else waits for admin approval.
    verified = models.BooleanField(default=False)
    verified_at = models.DateTimeField(null=True, blank=True)
    # What the vendor changed since staff last approved them: {field label: {old, new}}.
    pending_changes = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            base = slugify(self.name)[:120] or "vendor"
            slug, n = base, 2
            while Vendor.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                slug = f"{base}-{n}"
                n += 1
            self.slug = slug
        super().save(*args, **kwargs)

    # -- display helpers -----------------------------------------------------
    @property
    def status(self):
        """'suspended', 'verified' or 'pending'. Used by the staff desk."""
        if not self.user.is_active:
            return "suspended"
        return "verified" if self.verified else "pending"

    @property
    def initials(self):
        words = [w for w in re.split(r"\s+", self.name.strip()) if w]
        return "".join(w[0] for w in words[:2]).upper() or "?"

    @property
    def is_organiser(self):
        return self.role in (self.Role.ORGANISER, self.Role.BOTH)

    @property
    def role_label(self):
        return self.get_role_display()

    @property
    def whatsapp_number(self):
        return normalize_ng_phone(self.phone) if (self.phone or "").strip() else ""

    @property
    def whatsapp_url(self):
        number = self.whatsapp_number
        return f"https://wa.me/{number}" if number else ""

    @property
    def instagram_url(self):
        return f"https://instagram.com/{self.instagram}" if self.instagram else ""

    @property
    def tiktok_url(self):
        return f"https://www.tiktok.com/@{self.tiktok}" if self.tiktok else ""

    @property
    def twitter_url(self):
        return f"https://x.com/{self.twitter}" if self.twitter else ""

    @property
    def contact_links(self):
        """Every contact method this profile has filled in, ready to render as links."""
        links = []
        if self.whatsapp_url:
            links.append({"label": "WhatsApp", "url": self.whatsapp_url, "external": False})
        if self.instagram:
            links.append({"label": "Instagram", "url": self.instagram_url, "external": True})
        if self.tiktok:
            links.append({"label": "TikTok", "url": self.tiktok_url, "external": True})
        if self.twitter:
            links.append({"label": "Twitter/X", "url": self.twitter_url, "external": True})
        if self.website:
            links.append({"label": "Website", "url": self.website, "external": True})
        return links
