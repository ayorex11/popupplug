from django.contrib import messages
from django.contrib.auth import login
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from core.decorators import flag_invalid, login_required
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
        messages.success(request, "Welcome! Your vendor account is ready. Post your first pop-up.")
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
        form.save()
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
