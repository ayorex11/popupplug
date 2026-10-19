import re
import secrets
from urllib.parse import quote

from django.db import models
from django.utils import timezone

from events.models import Event

CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"  # no 0/O, 1/I/L: easy to read out at a stall


def normalize_phone(raw):
    """Return a Nigerian mobile number as '+234XXXXXXXXXX', or None if it isn't one.

    0801 234 5678, 801-234-5678, +234 801 234 5678 and 2348012345678 all become the same value,
    so one person can't enter several times just by formatting their number differently.
    """
    digits = re.sub(r"\D", "", raw or "")
    if digits.startswith("234"):
        digits = digits[3:]
    elif digits.startswith("0"):
        digits = digits[1:]
    if re.fullmatch(r"[789]\d{9}", digits):
        return f"+234{digits}"
    return None


def make_code():
    return "PP-" + "".join(secrets.choice(CODE_ALPHABET) for _ in range(6))


class Giveaway(models.Model):
    event = models.OneToOneField(Event, on_delete=models.CASCADE, related_name="giveaway")
    prize = models.CharField(max_length=140, help_text="Shown to shoppers, e.g. 'A ₦1,500 drink from Simmer & Sip'")
    winner_count = models.PositiveSmallIntegerField(default=5)
    backup_count = models.PositiveSmallIntegerField(default=4)
    opens_at = models.DateTimeField(default=timezone.now)
    closes_at = models.DateTimeField(help_text="Entries stop at this time (Lagos time)")
    is_active = models.BooleanField(default=True, help_text="Untick to hide the giveaway without deleting it")
    drawn_at = models.DateTimeField(null=True, blank=True, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Giveaway: {self.event.title}"

    @property
    def is_open(self):
        now = timezone.now()
        return self.is_active and self.drawn_at is None and self.opens_at <= now < self.closes_at

    @property
    def state(self):
        if not self.is_active:
            return "off"
        if self.drawn_at:
            return "drawn"
        now = timezone.now()
        if now < self.opens_at:
            return "upcoming"
        return "open" if now < self.closes_at else "closed"


class Entry(models.Model):
    class Result(models.TextChoices):
        NONE = "", "Entered"
        WINNER = "winner", "Winner"
        BACKUP = "backup", "Backup"
        DECLINED = "declined", "Declined / no reply"

    giveaway = models.ForeignKey(Giveaway, on_delete=models.CASCADE, related_name="entries")
    name = models.CharField(max_length=80)
    phone = models.CharField(max_length=14, help_text="Normalised +234 number")
    code = models.CharField(max_length=12, unique=True, default=make_code)
    ip_hash = models.CharField(max_length=16, blank=True, db_index=True)
    excluded = models.BooleanField(default=False, help_text="Looks fake or duplicate: left out of the draw")
    result = models.CharField(max_length=10, choices=Result.choices, blank=True, default="", db_index=True)
    backup_order = models.PositiveSmallIntegerField(null=True, blank=True)
    notified_at = models.DateTimeField(null=True, blank=True)
    claimed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]
        verbose_name_plural = "entries"
        constraints = [
            models.UniqueConstraint(fields=["giveaway", "phone"], name="uniq_giveaway_phone"),
        ]

    def __str__(self):
        return f"{self.code} · {self.name}"

    @property
    def first_name(self):
        return self.name.split()[0] if self.name.split() else self.name

    @property
    def wa_url(self):
        """Pre-filled WhatsApp message to this entrant (desk use)."""
        g, ev = self.giveaway, self.giveaway.event
        when = f"{ev.start_at:%A %-d %B}"
        if self.result == self.Result.WINNER:
            text = (
                f"Hi {self.first_name}! 🎉 You won in the PopUp Plug giveaway: {g.prize}. "
                f"Your code is {self.code}. Show it at the {ev.vendor.name} stall at {ev.venue} on {when}. "
                "Please reply within 24 hours to confirm you're coming, or we'll give your prize to someone else."
            )
        else:
            text = (
                f"Hi {self.first_name}! You're on the backup list for the PopUp Plug giveaway ({self.code}). "
                "If a winner can't make it we'll message you."
            )
        return f"https://wa.me/{self.phone.lstrip('+')}?text={quote(text)}"
