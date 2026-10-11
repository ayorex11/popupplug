"""The approval desk: staff-only pages for approving vendors and events, and the Instagram queue."""
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import user_passes_test
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from core import notifications
from events.caching import bump_version
from events.models import Event
from social import instagram, services
from social.models import SocialPost
from vendors.models import Vendor

staff_required = user_passes_test(lambda u: u.is_active and u.is_staff, login_url="login")


def _back(request, fallback):
    nxt = request.POST.get("next", "")
    if nxt.startswith("/desk/"):
        return redirect(nxt)
    return redirect(fallback)


# --------------------------------------------------------------------------- overview
@staff_required
def home(request):
    pending_vendors = Vendor.objects.filter(user__is_active=True, verified=False).select_related("user").annotate(
        event_total=Count("events", distinct=True),
        event_pending=Count("events", filter=Q(events__status=Event.Status.PENDING), distinct=True),
    ).order_by("created_at")
    pending_events = Event.objects.filter(status=Event.Status.PENDING).select_related("vendor", "area", "category").order_by("created_at")
    context = {
        "pending_vendors": pending_vendors[:5], "pending_vendor_count": pending_vendors.count(),
        "pending_events": pending_events[:5], "pending_event_count": pending_events.count(),
        "live_count": Event.objects.filter(status=Event.Status.PUBLISHED, end_at__gte=timezone.now()).count(),
        "vendor_count": Vendor.objects.count(),
        "social_ready": SocialPost.objects.filter(status__in=["draft", "failed"]).count(),
        "tab": "home",
    }
    return render(request, "desk/home.html", context)


# --------------------------------------------------------------------------- vendors
VENDOR_TABS = [("pending", "Pending"), ("verified", "Verified"), ("suspended", "Suspended"), ("all", "All")]


@staff_required
def vendors(request):
    tab = request.GET.get("tab", "pending")
    q = request.GET.get("q", "").strip()[:80]
    qs = Vendor.objects.select_related("user").annotate(
        event_total=Count("events", distinct=True),
        event_pending=Count("events", filter=Q(events__status=Event.Status.PENDING), distinct=True),
    ).order_by("-created_at")
    counts = {
        "pending": Vendor.objects.filter(user__is_active=True, verified=False).count(),
        "verified": Vendor.objects.filter(user__is_active=True, verified=True).count(),
        "suspended": Vendor.objects.filter(user__is_active=False).count(),
        "all": Vendor.objects.count(),
    }
    if tab == "pending":
        qs = qs.filter(user__is_active=True, verified=False).order_by("created_at")
    elif tab == "verified":
        qs = qs.filter(user__is_active=True, verified=True)
    elif tab == "suspended":
        qs = qs.filter(user__is_active=False)
    else:
        tab = "all"
    if q:
        qs = qs.filter(Q(name__icontains=q) | Q(user__email__icontains=q) | Q(instagram__icontains=q) | Q(phone__icontains=q))
    return render(request, "desk/vendors.html", {
        "vendors": qs[:100], "tab": "vendors", "subtab": tab, "q": q,
        "subtabs": [(k, label, counts[k]) for k, label in VENDOR_TABS],
    })


@staff_required
@require_POST
def vendor_action(request, pk):
    vendor = get_object_or_404(Vendor.objects.select_related("user"), pk=pk)
    action = request.POST.get("action")
    if action == "approve":
        vendor.verified, vendor.verified_at = True, timezone.now()
        vendor.save(update_fields=["verified", "verified_at"])
        notifications.notify_vendor_verified(vendor)
        services.queue_welcome_post(vendor)
        messages.success(request, f"{vendor.name} is verified. They can now publish instantly.")
    elif action == "unverify":
        vendor.verified = False
        vendor.save(update_fields=["verified"])
        messages.success(request, f"{vendor.name} is back to pending.")
    elif action == "suspend":
        vendor.user.is_active = False
        vendor.user.save(update_fields=["is_active"])
        vendor.events.filter(status=Event.Status.PUBLISHED).update(status=Event.Status.REJECTED, review_note="Vendor suspended")
        bump_version()
        messages.success(request, f"{vendor.name} is suspended and their events are hidden.")
    elif action == "reactivate":
        vendor.user.is_active = True
        vendor.user.save(update_fields=["is_active"])
        messages.success(request, f"{vendor.name} is active again.")
    else:
        messages.error(request, "Unknown action.")
    return _back(request, reverse("desk:vendors"))


# --------------------------------------------------------------------------- events
EVENT_TABS = [("pending", "Pending"), ("published", "Published"), ("rejected", "Rejected"), ("all", "All")]


@staff_required
def events(request):
    tab = request.GET.get("tab", "pending")
    q = request.GET.get("q", "").strip()[:80]
    base = Event.objects.select_related("vendor", "vendor__user", "area", "category")
    counts = {s: Event.objects.filter(status=s).count() for s in ("pending", "published", "rejected")}
    counts["all"] = sum(counts.values())
    qs = base.order_by("-created_at")
    if tab in counts and tab != "all":
        qs = base.filter(status=tab).order_by("created_at" if tab == "pending" else "-start_at")
    else:
        tab = "all"
    if q:
        qs = qs.filter(Q(title__icontains=q) | Q(vendor__name__icontains=q))
    return render(request, "desk/events.html", {
        "events": qs[:60], "tab": "events", "subtab": tab, "q": q,
        "subtabs": [(k, label, counts[k]) for k, label in EVENT_TABS],
    })


@staff_required
@require_POST
def event_action(request, pk):
    event = get_object_or_404(Event.objects.select_related("vendor", "vendor__user", "area"), pk=pk)
    action = request.POST.get("action")
    now = timezone.now()
    if action == "approve":
        event.status, event.review_note, event.reviewed_at = Event.Status.PUBLISHED, "", now
        event.save()
        notifications.notify_vendor_event_live(event)
        services.queue_event_post(event)
        messages.success(request, f"Published: {event.title}")
    elif action == "reject":
        event.status, event.reviewed_at = Event.Status.REJECTED, now
        event.review_note = request.POST.get("note", "").strip()[:200]
        event.save()
        notifications.notify_vendor_event_rejected(event)
        messages.success(request, f"Rejected: {event.title}")
    elif action == "unpublish":
        event.status, event.reviewed_at = Event.Status.PENDING, now
        event.save()
        messages.success(request, f"Moved back to pending: {event.title}")
    else:
        messages.error(request, "Unknown action.")
    return _back(request, reverse("desk:events"))


# --------------------------------------------------------------------------- instagram
@staff_required
def social(request):
    tab = request.GET.get("tab", "ready")
    qs = SocialPost.objects.select_related("event", "vendor")
    if tab == "posted":
        qs = qs.filter(status="posted")
    elif tab == "skipped":
        qs = qs.filter(status="skipped")
    else:
        tab = "ready"
        qs = qs.filter(status__in=["draft", "failed", "posting"])
    return render(request, "desk/social.html", {
        "posts": qs[:40], "tab": "social", "subtab": tab,
        "ig_enabled": settings.INSTAGRAM_ENABLED, "ig_ready": instagram.is_configured(),
        "autopost": settings.INSTAGRAM_AUTOPOST, "dry_run": settings.INSTAGRAM_DRY_RUN,
        "days_left": instagram.token_days_left(), "handle": settings.INSTAGRAM_HANDLE,
    })


@staff_required
@require_POST
def social_action(request, pk):
    post = get_object_or_404(SocialPost, pk=pk)
    action = request.POST.get("action")
    if action == "post":
        post.caption = request.POST.get("caption", post.caption)[:2200]
        post.save(update_fields=["caption"])
        result = services.publish(post.pk)
        (messages.success if result.startswith(("Posted", "Dry run")) else messages.error)(request, result)
    elif action == "manual":
        post.status, post.posted_at = SocialPost.Status.POSTED, timezone.now()
        post.note = "Posted by hand"
        post.save()
        messages.success(request, "Marked as posted.")
    elif action == "skip":
        post.status = SocialPost.Status.SKIPPED
        post.save(update_fields=["status"])
        messages.success(request, "Skipped.")
    elif action == "restore":
        post.status = SocialPost.Status.DRAFT
        post.save(update_fields=["status"])
    elif action == "regenerate":
        services.regenerate(post)
        messages.success(request, "Card and caption rebuilt.")
    return _back(request, reverse("desk:social"))
