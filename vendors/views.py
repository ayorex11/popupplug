from django.contrib import messages
from django.contrib.auth import login
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from core.changes import form_changes, merge_changes
from core.decorators import flag_invalid, login_required
from core.notifications import notify_vendor_profile_edited
from events.models import Event

from .forms import VendorProfileForm, VendorSignupForm
from .models import Vendor


def signup(request):
    if request.user.is_authenticated:
        return redirect("vendors:dashboard")
    form = VendorSignupForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        login(request, user)
        messages.success(request, "Welcome! Your account is ready. Post your first event." if user.vendor.is_organiser
                         else "Welcome! Your vendor account is ready. Post your first pop-up.")
        return redirect("vendors:dashboard")
    flag_invalid(request, form)
    return render(request, "vendors/signup.html", {"form": form})


@login_required
def dashboard(request):
    vendor = getattr(request.user, "vendor", None)
    if vendor is None:
        messages.info(request, "Staff accounts don't have a vendor profile.")
        return redirect("events:home")
    events = vendor.events.select_related("area", "category").order_by("-start_at")
    return render(request, "vendors/dashboard.html", {"vendor": vendor, "events": events, "now": timezone.now()})


@login_required
def edit_profile(request):
    vendor = get_object_or_404(Vendor, user=request.user)
    form = VendorProfileForm(request.POST or None, instance=vendor)
    if request.method == "POST" and form.is_valid():
        if not form.has_changed():
            messages.info(request, "No changes to save.")
            return redirect("vendors:dashboard")
        was_verified = vendor.verified
        changes = form_changes(form)
        vendor = form.save(commit=False)
        if was_verified:
            vendor.verified = False  # profile changes have to be re-approved
        if was_verified or vendor.pending_changes:
            vendor.pending_changes = merge_changes(vendor.pending_changes, changes)
        vendor.save()
        if was_verified:
            notify_vendor_profile_edited(vendor)
            messages.success(request, "Profile updated. It's back in review and your Verified badge returns once we re-approve it, usually within a day. Your live events stay up.")
        else:
            messages.success(request, "Profile updated.")
        return redirect("vendors:dashboard")
    flag_invalid(request, form)
    return render(request, "vendors/profile_form.html", {"form": form})


def public_profile(request, slug):
    vendor = get_object_or_404(Vendor, slug=slug)
    now = timezone.now()
    upcoming = vendor.events.filter(status=Event.Status.PUBLISHED, end_at__gte=now).order_by("start_at")
    past = vendor.events.filter(status=Event.Status.PUBLISHED, end_at__lt=now).order_by("-start_at")[:6]
    return render(request, "vendors/profile.html", {"vendor": vendor, "upcoming": upcoming, "past": past})
