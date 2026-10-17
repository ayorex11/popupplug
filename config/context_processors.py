from django.conf import settings


def site(request):
    """Brand info for every template, plus pending counts for the staff nav badge."""
    ctx = {"SITE_NAME": settings.SITE_NAME, "SITE_URL": settings.SITE_URL, "INSTAGRAM_HANDLE": settings.INSTAGRAM_HANDLE,
           "CANONICAL_URL": settings.SITE_URL + request.path}
    user = getattr(request, "user", None)
    if user is not None and user.is_authenticated and user.is_staff:
        from events.models import Event
        from vendors.models import Vendor
        ctx["staff_pending_vendors"] = Vendor.objects.filter(user__is_active=True, verified=False).count()
        ctx["staff_pending_events"] = Event.objects.filter(status=Event.Status.PENDING).count()
        ctx["staff_pending_total"] = ctx["staff_pending_vendors"] + ctx["staff_pending_events"]
    return ctx
