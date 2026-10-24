"""Email notifications.

Rules this module follows:
* Never break the request that triggered the email. Every failure is logged and swallowed.
* Never send before the database transaction commits (so the dashboard link works).
* Never block the page: with NOTIFY_ASYNC (default) the SMTP call runs in a background thread.
* Recipients are computed up front, in the request thread, so the background thread
  never touches the database.
"""
import logging
import threading
from contextlib import contextmanager

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.mail import EmailMultiAlternatives
from django.db import transaction
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone

log = logging.getLogger(__name__)
_state = threading.local()


@contextmanager
def muted():
    """Suppress all notifications inside the block (used by seed commands)."""
    previous = getattr(_state, "muted", False)
    _state.muted = True
    try:
        yield
    finally:
        _state.muted = previous


def absolute_url(path):
    if path.startswith(("http://", "https://")):
        return path
    return f"{settings.SITE_URL}{path}"


def admin_recipients():
    """ADMIN_NOTIFY_EMAILS if set, otherwise every active staff user that has an email."""
    if settings.ADMIN_NOTIFY_EMAILS:
        return list(dict.fromkeys(settings.ADMIN_NOTIFY_EMAILS))
    User = get_user_model()
    emails = User.objects.filter(is_active=True, is_staff=True).exclude(email="").values_list("email", flat=True)
    return sorted({e.strip() for e in emails if e.strip()})


def _deliver(subject, text, html, to):
    try:
        message = EmailMultiAlternatives(subject, text, settings.DEFAULT_FROM_EMAIL, to)
        message.attach_alternative(html, "text/html")
        message.send()
        log.info("Email sent: %r to %d recipient(s)", subject, len(to))
    except Exception:  # noqa: BLE001 - an email problem must never surface to a visitor
        log.exception("Could not send email %r", subject)


def _dispatch(subject, text, html, to):
    if settings.NOTIFY_ASYNC:
        threading.Thread(target=_deliver, args=(subject, text, html, to), daemon=True).start()
    else:
        _deliver(subject, text, html, to)


def send_card_email(subject, heading, intro, rows, to, button_label="", button_url="", footer=""):
    """Render and send one branded email. `rows` is a list of (label, value) pairs."""
    to = [t for t in (to or []) if t]
    if not to or getattr(_state, "muted", False):
        return False
    context = {
        "heading": heading, "intro": intro, "rows": [(k, v) for k, v in rows if v],
        "button_label": button_label, "button_url": absolute_url(button_url) if button_url else "",
        "footer": footer, "SITE_NAME": settings.SITE_NAME, "SITE_URL": settings.SITE_URL,
    }
    html = render_to_string("emails/card.html", context)
    lines = [heading, "", intro, ""] + [f"{k}: {v}" for k, v in context["rows"]]
    if button_url:
        lines += ["", f"{button_label}: {context['button_url']}"]
    if footer:
        lines += ["", footer]
    text = "\n".join(lines)
    transaction.on_commit(lambda: _dispatch(subject, text, html, to))
    return True


# ---------------------------------------------------------------------------
# Messages to you (the admin)
# ---------------------------------------------------------------------------
def notify_new_vendor(vendor):
    when = timezone.localtime(vendor.created_at).strftime("%a %d %b, %I:%M %p")
    kind = "organiser" if vendor.role == "organiser" else "vendor"
    return send_card_email(
        subject=f"New {kind} signed up: {vendor.name}",
        heading=f"New {kind} to review",
        intro="Someone just signed up. Check their Instagram or WhatsApp, then approve them in your desk."
              + (" Organisers can ask vendors for booth fees, so check their past events first." if vendor.is_organiser else ""),
        rows=[
            ("Business", vendor.name),
            ("Role", vendor.role_label),
            ("WhatsApp", f"{vendor.phone}  ({vendor.whatsapp_url})" if vendor.phone else ""),
            ("Email", vendor.user.email),
            ("Instagram", f"@{vendor.instagram}  ({vendor.instagram_url})" if vendor.instagram else ""),
            ("TikTok", f"@{vendor.tiktok}  ({vendor.tiktok_url})" if vendor.tiktok else ""),
            ("Twitter/X", f"@{vendor.twitter}  ({vendor.twitter_url})" if vendor.twitter else ""),
            ("Website", vendor.website),
            ("Signed up", when),
        ],
        to=admin_recipients(),
        button_label="Review in your desk",
        button_url=reverse("desk:vendors") + "?tab=pending",
        footer="You get this email because you're an admin of PopUp Plug.",
    )


def _change_rows(changes):
    return [(label, f"{c['old']}  →  {c['new']}") for label, c in (changes or {}).items()]


def notify_vendor_profile_edited(vendor):
    return send_card_email(
        subject=f"Profile edited, re-approve: {vendor.name}",
        heading="Edited profile waiting for approval",
        intro=f"{vendor.name} changed their profile, so they're unverified again until you approve it.",
        rows=[
            *_change_rows(vendor.pending_changes),
            ("Business", vendor.name),
            ("Role", vendor.role_label),
            ("WhatsApp", f"{vendor.phone}  ({vendor.whatsapp_url})" if vendor.phone else ""),
            ("Instagram", f"@{vendor.instagram}  ({vendor.instagram_url})" if vendor.instagram else ""),
            ("TikTok", f"@{vendor.tiktok}  ({vendor.tiktok_url})" if vendor.tiktok else ""),
            ("Twitter/X", f"@{vendor.twitter}  ({vendor.twitter_url})" if vendor.twitter else ""),
            ("Website", vendor.website),
        ],
        to=admin_recipients(),
        button_label="Review in your desk",
        button_url=reverse("desk:vendors") + "?tab=pending",
        footer="You get this email because you're an admin of PopUp Plug.",
    )


def notify_password_reset(user, url):
    return send_card_email(
        subject="Reset your PopUp Plug password",
        heading="Reset your password",
        intro="Someone asked to reset the password for this account. Use the button to choose a new one. "
              "The link works for a few hours. If it wasn't you, ignore this email and your password stays the same.",
        rows=[("Account", user.email)],
        to=[user.email],
        button_label="Choose a new password",
        button_url=url,
        footer="You get this email because a password reset was requested on PopUp Plug.",
    )


def notify_event_pending(event, edited=False):
    start = timezone.localtime(event.start_at).strftime("%a %d %b, %I:%M %p")
    return send_card_email(
        subject=f"{'Edited event' if edited else 'New event'} to approve: {event.title}",
        heading="Event waiting for approval" if not edited else "Edited event waiting for approval",
        intro=f"{event.vendor.name} {'changed' if edited else 'posted'} a pop-up. It's hidden until you approve it.",
        rows=[
            ("Event", event.title),
            ("Vendor", event.vendor.name + ("" if event.vendor.verified else "  (not verified yet)")),
            ("When", start),
            ("Where", f"{event.venue}, {event.area.name}"),
            ("Category", event.category.name),
            *(_change_rows(event.pending_changes) if edited else []),
        ],
        to=admin_recipients(),
        button_label="Review in your desk",
        button_url=reverse("desk:events") + "?tab=pending",
        footer="You get this email because you're an admin of PopUp Plug.",
    )


# ---------------------------------------------------------------------------
# Messages to vendors
# ---------------------------------------------------------------------------
def notify_vendor_event_live(event):
    return send_card_email(
        subject=f"Your pop-up is live: {event.title}",
        heading="Your pop-up is live",
        intro="Good news, it's now visible to shoppers. Share the link on your Instagram, Twitter and WhatsApp status.",
        rows=[("Event", event.title), ("Link", absolute_url(event.get_absolute_url()))],
        to=[event.vendor.user.email],
        button_label="View your event",
        button_url=event.get_absolute_url(),
    )


def notify_vendor_event_rejected(event):
    return send_card_email(
        subject=f"About your pop-up: {event.title}",
        heading="We couldn't publish your pop-up",
        intro=event.review_note or "It didn't meet our listing guidelines this time.",
        rows=[("Event", event.title)],
        to=[event.vendor.user.email],
        button_label="Edit and resubmit",
        button_url=reverse("events:edit", args=[event.slug]),
        footer="Fix what's mentioned above and submit again. We review it quickly.",
    )


def notify_vendor_verified(vendor):
    return send_card_email(
        subject="You're verified on PopUp Plug",
        heading="You're verified",
        intro="Your account is approved. From now on your pop-ups go live as soon as you post them.",
        rows=[("Business", vendor.name)],
        to=[vendor.user.email],
        button_label="Post a pop-up",
        button_url=reverse("events:create"),
    )
