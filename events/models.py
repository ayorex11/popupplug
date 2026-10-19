import uuid

from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist
from django.db import models
from django.urls import reverse
from django.utils import timezone
from django.utils.text import slugify

from vendors.models import Vendor


def event_image_path(instance, filename):
    # Randomized path: never trust user-supplied filenames, and avoid collisions.
    return f"events/{timezone.now():%Y/%m}/{uuid.uuid4().hex}.webp"


class City(models.Model):
    """Lagos only for now. Kept as a model so expansion is data, not a rewrite."""

    name = models.CharField(max_length=60, unique=True)
    slug = models.SlugField(unique=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name_plural = "cities"

    def __str__(self):
        return self.name


class Area(models.Model):
    """A neighborhood within a city (Lekki, Yaba, Ikeja...)."""

    city = models.ForeignKey(City, on_delete=models.CASCADE, related_name="areas")
    name = models.CharField(max_length=80)
    slug = models.SlugField()

    class Meta:
        ordering = ["name"]
        unique_together = [("city", "slug")]

    def __str__(self):
        return self.name


class Category(models.Model):
    name = models.CharField(max_length=60, unique=True)
    slug = models.SlugField(unique=True)

    class Meta:
        ordering = ["name"]
        verbose_name_plural = "categories"

    def __str__(self):
        return self.name


class Event(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending review"
        PUBLISHED = "published", "Published"
        REJECTED = "rejected", "Rejected"

    vendor = models.ForeignKey(Vendor, on_delete=models.CASCADE, related_name="events")
    title = models.CharField(max_length=140)
    slug = models.SlugField(max_length=170, unique=True, blank=True)
    category = models.ForeignKey(Category, on_delete=models.PROTECT, related_name="events")
    area = models.ForeignKey(Area, on_delete=models.PROTECT, related_name="events")
    venue = models.CharField(max_length=160, help_text="Venue name and street, e.g. 'The Hub, 12 Admiralty Way, Lekki Phase 1'")
    description = models.TextField(max_length=3000)
    cover_image = models.ImageField(upload_to=event_image_path)
    start_at = models.DateTimeField(db_index=True)
    end_at = models.DateTimeField(db_index=True)
    is_free_entry = models.BooleanField("Free entry", default=True)
    entry_note = models.CharField(max_length=120, blank=True, help_text="Optional, e.g. 'Free before 2pm' or 'Gate fee ₦2,000'")
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING, db_index=True)
    interested_count = models.PositiveIntegerField(default=0)  # denormalized for fast lists
    review_note = models.CharField(max_length=200, blank=True, help_text="Shown to the vendor, e.g. why an event was rejected")
    reviewed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["start_at"]
        indexes = [
            models.Index(fields=["status", "start_at"]),
            models.Index(fields=["status", "area", "start_at"]),
            models.Index(fields=["status", "category", "start_at"]),
        ]

    def __str__(self):
        return self.title

    def get_absolute_url(self):
        return reverse("events:detail", kwargs={"slug": self.slug})

    def save(self, *args, **kwargs):
        if not self.slug:
            base = slugify(self.title)[:110] or "event"
            when = timezone.localtime(self.start_at).strftime("%b-%d").lower() if self.start_at else ""
            base = f"{base}-{when}".strip("-")
            slug, n = base, 2
            while Event.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                slug = f"{base}-{n}"
                n += 1
            self.slug = slug
        super().save(*args, **kwargs)

    @property
    def is_published(self):
        return self.status == self.Status.PUBLISHED

    @property
    def open_giveaway(self):
        """The giveaway if entries are open right now, else None (safe when none exists)."""
        try:
            g = self.giveaway
        except ObjectDoesNotExist:
            return None
        return g if g.is_open else None

    @property
    def is_past(self):
        return self.end_at < timezone.now()


class Interested(models.Model):
    """One 'I'm interested' per user (or per anonymous session) per event."""

    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name="interests")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.CASCADE)
    session_key = models.CharField(max_length=40, blank=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["event", "user"], condition=models.Q(user__isnull=False), name="uniq_interest_event_user"),
            models.UniqueConstraint(fields=["event", "session_key"], condition=~models.Q(session_key=""), name="uniq_interest_event_session"),
        ]

    def __str__(self):
        return f"Interest in {self.event_id}"
