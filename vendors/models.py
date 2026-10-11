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
    """A business or individual who posts pop-up events."""

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="vendor")
    name = models.CharField("Business name", max_length=120)
    slug = models.SlugField(max_length=140, unique=True, blank=True)
    bio = models.CharField(max_length=300, blank=True)
    phone = models.CharField(max_length=20, help_text="WhatsApp-able number, e.g. 08012345678")
    instagram = models.CharField(max_length=60, blank=True, help_text="Handle without the @")
    twitter = models.CharField("Twitter/X", max_length=60, blank=True, help_text="Handle without the @")
    # Verified vendors publish instantly; everyone else waits for admin approval.
    verified = models.BooleanField(default=False)
    verified_at = models.DateTimeField(null=True, blank=True)
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
    def whatsapp_number(self):
        return normalize_ng_phone(self.phone)

    @property
    def whatsapp_url(self):
        return f"https://wa.me/{self.whatsapp_number}"

    @property
    def instagram_url(self):
        return f"https://instagram.com/{self.instagram}" if self.instagram else ""

    @property
    def twitter_url(self):
        return f"https://x.com/{self.twitter}" if self.twitter else ""
