from django import template
from django.utils import timezone
from django.utils.safestring import mark_safe

from core import seo

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


@register.simple_tag
def jsonld(kind, obj=None):
    """{% jsonld "site" %}, {% jsonld "event" event %}. Emits a JSON-LD script tag."""
    if kind == "site":
        data = seo.site_schema()
    elif kind == "event":
        data = seo.event_schema(obj)
    else:
        return ""
    return mark_safe(f'<script type="application/ld+json">{seo.dumps(data)}</script>')
