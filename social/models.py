from django.db import models

from events.models import Event
from vendors.models import Vendor


class InstagramToken(models.Model):
    """The long-lived Instagram token (single row). Seeded from INSTAGRAM_ACCESS_TOKEN,
    then refreshed automatically so you don't have to touch it every 60 days."""

    access_token = models.TextField()
    expires_at = models.DateTimeField(null=True, blank=True)
    refreshed_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return "Instagram token"


class SocialPost(models.Model):
    class Kind(models.TextChoices):
        EVENT = "event", "Event"
        WELCOME = "welcome", "Welcome vendor"

    class Status(models.TextChoices):
        DRAFT = "draft", "Ready to post"
        POSTING = "posting", "Posting"
        POSTED = "posted", "Posted"
        FAILED = "failed", "Failed"
        SKIPPED = "skipped", "Skipped"

    kind = models.CharField(max_length=10, choices=Kind.choices)
    event = models.ForeignKey(Event, null=True, blank=True, on_delete=models.SET_NULL, related_name="social_posts")
    vendor = models.ForeignKey(Vendor, null=True, blank=True, on_delete=models.SET_NULL, related_name="social_posts")
    caption = models.TextField(max_length=2200)
    image = models.ImageField(upload_to="social/%Y/%m/")
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.DRAFT, db_index=True)
    ig_container_id = models.CharField(max_length=64, blank=True)
    ig_media_id = models.CharField(max_length=64, blank=True)
    permalink = models.URLField(blank=True)
    note = models.CharField(max_length=300, blank=True)  # last error or dry-run result
    created_at = models.DateTimeField(auto_now_add=True)
    posted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.get_kind_display()} post #{self.pk} ({self.status})"
