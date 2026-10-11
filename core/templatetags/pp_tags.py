from django import template
from django.utils import timezone

register = template.Library()


@register.filter
def when_range(event):
    """'Sat 18 Oct, 12:00 PM - 8:00 PM' (or with both dates when the event spans days)."""
    start, end = timezone.localtime(event.start_at), timezone.localtime(event.end_at)
    fmt_t = lambda d: d.strftime("%I:%M %p").lstrip("0")  # noqa: E731
    if start.date() == end.date():
        return f"{start:%a %d %b}, {fmt_t(start)} - {fmt_t(end)}"
    return f"{start:%a %d %b}, {fmt_t(start)} - {end:%a %d %b}, {fmt_t(end)}"


@register.filter
def day_abbr(dt):
    return timezone.localtime(dt).strftime("%a").upper()


@register.filter
def day_num(dt):
    return timezone.localtime(dt).strftime("%d").lstrip("0")


@register.filter
def month_abbr(dt):
    return timezone.localtime(dt).strftime("%b").upper()


@register.filter
def tint(obj_or_id):
    """Pick one of four soft pill colours, stable per category."""
    pk = getattr(obj_or_id, "pk", obj_or_id) or 0
    return ("coral", "butter", "matcha", "lilac")[int(pk) % 4]
