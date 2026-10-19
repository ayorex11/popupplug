import hashlib

from django.conf import settings
from django.core.cache import cache
from django.db import IntegrityError, transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_http_methods

from events.models import Event

from .forms import EntryForm
from .models import Entry

# Mobile carriers put many people behind one IP, so this is deliberately generous.
# It stops scripts, not a busy campus.
IP_LIMIT, IP_WINDOW = 15, 3600


def client_ip(request):
    fwd = request.META.get("HTTP_X_FORWARDED_FOR", "")
    return (fwd.split(",")[0].strip() if fwd else request.META.get("REMOTE_ADDR", "")) or "unknown"


def ip_hash(ip):
    return hashlib.sha256(f"{settings.SECRET_KEY}:{ip}".encode()).hexdigest()[:16]


def _session_key(giveaway):
    return f"giveaway_{giveaway.pk}"


def _respond(request, event, giveaway, form, ok=False, entry=None, message="", status=200):
    if request.headers.get("x-requested-with") == "XMLHttpRequest":
        data = {"ok": ok, "message": message}
        if entry:
            data["code"] = entry.code
        if not ok:
            data["errors"] = {k: v[0] for k, v in form.errors.items()} if form is not None else {}
        return JsonResponse(data, status=status)
    return render(request, "giveaways/enter.html", {
        "event": event, "giveaway": giveaway, "form": form, "entry": entry, "message": message,
    }, status=status)


@require_http_methods(["GET", "POST"])
def enter(request, slug):
    event = get_object_or_404(Event.objects.select_related("vendor", "giveaway"), slug=slug, status=Event.Status.PUBLISHED)
    giveaway = getattr(event, "giveaway", None)
    if giveaway is None or not giveaway.is_active:
        return _respond(request, event, None, None, message="There's no giveaway for this pop-up.", status=404)

    skey = _session_key(giveaway)
    already = request.session.get(skey)
    if request.method == "GET":
        entry = Entry.objects.filter(code=already, giveaway=giveaway).first() if already else None
        return render(request, "giveaways/enter.html", {"event": event, "giveaway": giveaway, "form": EntryForm(), "entry": entry})

    form = EntryForm(request.POST)
    if not giveaway.is_open:
        return _respond(request, event, giveaway, form, message="Entries for this giveaway aren't open right now.", status=400)

    if form.data.get("website"):  # honeypot tripped: pretend it worked, record nothing
        fake = Entry(code="PP-" + "X" * 6)
        return _respond(request, event, giveaway, form, ok=True, entry=fake, message="You're in!")

    ip = client_ip(request)
    ih = ip_hash(ip)
    rl_key = f"giveaway-ip:{giveaway.pk}:{ih}"
    cache.add(rl_key, 0, IP_WINDOW)
    try:
        hits = cache.incr(rl_key)
    except ValueError:
        hits = 1
    if hits > IP_LIMIT:
        return _respond(request, event, giveaway, form, message="Too many entries from this connection. Please try again later.", status=429)

    # Same browser session already entered: show the existing ticket instead of a second one.
    if already:
        entry = Entry.objects.filter(code=already, giveaway=giveaway).first()
        if entry:
            return _respond(request, event, giveaway, form, ok=True, entry=entry, message="You're already in.")

    if not form.is_valid():
        return _respond(request, event, giveaway, form, message="Please fix the highlighted fields.", status=400)

    phone, name = form.cleaned_data["phone"], form.cleaned_data["name"]
    existing = Entry.objects.filter(giveaway=giveaway, phone=phone).first()
    if existing:
        request.session[skey] = existing.code
        return _respond(request, event, giveaway, form, ok=True, entry=existing, message="That number is already entered. Here's your ticket.")

    entry = None
    for _ in range(5):  # retry on the (very unlikely) code collision
        try:
            with transaction.atomic():
                entry = Entry.objects.create(giveaway=giveaway, name=name, phone=phone, ip_hash=ih)
            break
        except IntegrityError:
            entry = Entry.objects.filter(giveaway=giveaway, phone=phone).first()
            if entry:
                break
    if entry is None:
        return _respond(request, event, giveaway, form, message="Something went wrong. Please try again.", status=500)

    request.session[skey] = entry.code
    return _respond(request, event, giveaway, form, ok=True, entry=entry, message="You're in!")
