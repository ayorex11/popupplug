from datetime import timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db import IntegrityError, transaction
from django.db.models import F, Q
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from core.notifications import notify_event_pending
from social import services as social_services
from vendors.models import Vendor

from .caching import cache_public
from .forms import EventForm
from .models import Area, Category, Event, Interested

PAGE_SIZE = 12


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def published():
    return Event.objects.filter(status=Event.Status.PUBLISHED).select_related("vendor", "area", "category")


def weekend_window(now=None):
    """Return (start, end) for 'this weekend' in Lagos time (Fri 00:00 to Sun 23:59)."""
    now = timezone.localtime(now or timezone.now())
    midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
    weekday = now.weekday()  # Mon=0 ... Sun=6
    start = midnight + timedelta(days=4 - weekday) if weekday <= 4 else midnight
    end = midnight + timedelta(days=7 - weekday) - timedelta(microseconds=1)
    return max(start, now), end


def vendor_for(user):
    return getattr(user, "vendor", None)


# ---------------------------------------------------------------------------
# Public pages
# ---------------------------------------------------------------------------
@cache_public
def home(request):
    now = timezone.now()
    w_start, w_end = weekend_window(now)
    this_weekend = published().filter(start_at__lte=w_end, end_at__gte=w_start)[:6]
    upcoming = published().filter(end_at__gte=now).exclude(pk__in=[e.pk for e in this_weekend])[:6]
    return render(request, "events/home.html", {
        "this_weekend": this_weekend,
        "upcoming": upcoming,
        "categories": Category.objects.all(),
        "areas": Area.objects.filter(city__is_active=True),
    })


@cache_public
def event_list(request):
    now = timezone.now()
    qs = published()

    when = request.GET.get("when", "upcoming")
    if when == "today":
        end_of_day = timezone.localtime(now).replace(hour=23, minute=59, second=59, microsecond=999999)
        qs = qs.filter(start_at__lte=end_of_day, end_at__gte=now)
    elif when == "weekend":
        w_start, w_end = weekend_window(now)
        qs = qs.filter(start_at__lte=w_end, end_at__gte=w_start)
    elif when == "week":
        qs = qs.filter(start_at__lte=now + timedelta(days=7), end_at__gte=now)
    elif when == "past":
        qs = qs.filter(end_at__lt=now).order_by("-start_at")
    else:
        when = "upcoming"
        qs = qs.filter(end_at__gte=now)

    area = request.GET.get("area", "")
    if area:
        qs = qs.filter(area__slug=area)
    category = request.GET.get("category", "")
    if category:
        qs = qs.filter(category__slug=category)
    if request.GET.get("free") == "1":
        qs = qs.filter(is_free_entry=True)

    q = request.GET.get("q", "").strip()[:80]
    if q:
        qs = qs.filter(Q(title__icontains=q) | Q(description__icontains=q) | Q(vendor__name__icontains=q))

    page = Paginator(qs, PAGE_SIZE).get_page(request.GET.get("page"))
    params = request.GET.copy()
    params.pop("page", None)
    return render(request, "events/event_list.html", {
        "page": page,
        "when": when, "area": area, "category": category, "q": q,
        "free": request.GET.get("free") == "1",
        "categories": Category.objects.all(),
        "areas": Area.objects.filter(city__is_active=True),
        "querystring": params.urlencode(),
    })


def event_detail(request, slug):
    event = get_object_or_404(Event.objects.select_related("vendor", "area", "category"), slug=slug)
    vendor = vendor_for(request.user) if request.user.is_authenticated else None
    can_manage = request.user.is_staff or (vendor is not None and event.vendor_id == vendor.pk)
    if not event.is_published and not can_manage:
        raise Http404()

    interested = False
    if request.user.is_authenticated:
        interested = Interested.objects.filter(event=event, user=request.user).exists()
    elif request.session.session_key:
        interested = Interested.objects.filter(event=event, session_key=request.session.session_key).exists()

    more = published().filter(area=event.area, end_at__gte=timezone.now()).exclude(pk=event.pk)[:3]
    return render(request, "events/event_detail.html", {
        "event": event, "can_manage": can_manage, "interested": interested, "more": more,
    })


@require_POST
def toggle_interested(request, slug):
    event = get_object_or_404(Event, slug=slug, status=Event.Status.PUBLISHED)

    if request.user.is_authenticated:
        lookup = {"event": event, "user": request.user}
        create_kwargs = {"user": request.user}
    else:
        if not request.session.session_key:
            request.session.create()
        lookup = {"event": event, "session_key": request.session.session_key}
        create_kwargs = {"session_key": request.session.session_key}

    with transaction.atomic():
        existing = Interested.objects.filter(**lookup).first()
        if existing:
            existing.delete()
            Event.objects.filter(pk=event.pk, interested_count__gt=0).update(interested_count=F("interested_count") - 1)
            state = False
        else:
            try:
                Interested.objects.create(event=event, **create_kwargs)
                Event.objects.filter(pk=event.pk).update(interested_count=F("interested_count") + 1)
            except IntegrityError:
                pass  # double-click race: already counted
            state = True

    event.refresh_from_db(fields=["interested_count"])
    if request.headers.get("x-requested-with") == "XMLHttpRequest":
        return JsonResponse({"interested": state, "count": event.interested_count})
    return redirect(event.get_absolute_url())


# ---------------------------------------------------------------------------
# Vendor actions
# ---------------------------------------------------------------------------
@login_required
def event_create(request):
    vendor = vendor_for(request.user)
    if vendor is None:
        messages.error(request, "Only vendor accounts can post events.")
        return redirect("events:home")

    form = EventForm(request.POST or None, request.FILES or None, vendor=vendor)
    if request.method == "POST" and form.is_valid():
        event = form.save(commit=False)
        event.vendor = vendor
        event.status = Event.Status.PUBLISHED if vendor.verified else Event.Status.PENDING
        event.save()
        if event.is_published:
            social_services.queue_event_post(event)
            messages.success(request, "Your pop-up is live!")
        else:
            notify_event_pending(event)
            messages.success(request, "Submitted! We review new vendors' first events, usually within a day.")
        return redirect("vendors:dashboard")
    return render(request, "events/event_form.html", {"form": form, "editing": False})


@login_required
def event_edit(request, slug):
    vendor = vendor_for(request.user)
    event = get_object_or_404(Event, slug=slug, vendor=vendor) if vendor else None
    if event is None:
        raise Http404()

    form = EventForm(request.POST or None, request.FILES or None, instance=event, vendor=vendor)
    if request.method == "POST" and form.is_valid():
        event = form.save(commit=False)
        if not vendor.verified:
            event.status = Event.Status.PENDING  # edits by unverified vendors are re-reviewed
        event.save()
        if not vendor.verified:
            notify_event_pending(event, edited=True)
        messages.success(request, "Event updated.")
        return redirect("vendors:dashboard")
    return render(request, "events/event_form.html", {"form": form, "editing": True, "event": event})


@login_required
@require_POST
def event_delete(request, slug):
    vendor = vendor_for(request.user)
    event = get_object_or_404(Event, slug=slug, vendor=vendor) if vendor else None
    if event is None:
        raise Http404()
    event.delete()
    messages.success(request, "Event deleted.")
    return redirect("vendors:dashboard")
