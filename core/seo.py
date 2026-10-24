"""SEO plumbing: robots.txt, sitemap.xml, structured data (JSON-LD) and noindex headers."""
import json
import re
from datetime import timedelta
from xml.sax.saxutils import escape

from django.conf import settings
from django.http import HttpResponse
from django.templatetags.static import static
from django.urls import reverse
from django.utils import timezone

# Pages that must never appear in search: staff tools, auth, vendor-only screens, POST endpoints.
PRIVATE_PATHS = re.compile(
    r"^/(desk|admin|login|logout|password-reset|reset)(/|$)"
    r"|^/vendors/(dashboard|profile/edit)/"
    r"|^/events/new/"
    r"|^/e/[^/]+/(edit|delete|interested)/"
)


def absolute(path):
    return f"{settings.SITE_URL}{path}"


def absolute_media(url):
    return url if url.startswith("http") else absolute(url)


# ---------------------------------------------------------------------------
# robots.txt and sitemap.xml
# ---------------------------------------------------------------------------
def robots_txt(request):
    lines = [
        "User-agent: *",
        "Disallow: /desk/",
        "Disallow: /admin/",
        "Disallow: /login/",
        "Disallow: /logout/",
        "Disallow: /vendors/dashboard/",
        "Disallow: /vendors/profile/edit/",
        "Disallow: /events/new/",
        "Disallow: /e/*/edit/",
        "Disallow: /e/*/delete/",
        "Disallow: /e/*/interested/",
        "",
        f"Sitemap: {absolute('/sitemap.xml')}",
        "",
    ]
    return HttpResponse("\n".join(lines), content_type="text/plain")


def _url(loc, lastmod=None, changefreq=None, priority=None):
    parts = [f"<loc>{escape(loc)}</loc>"]
    if lastmod:
        parts.append(f"<lastmod>{lastmod:%Y-%m-%d}</lastmod>")
    if changefreq:
        parts.append(f"<changefreq>{changefreq}</changefreq>")
    if priority:
        parts.append(f"<priority>{priority}</priority>")
    return "<url>" + "".join(parts) + "</url>"


def sitemap_xml(request):
    from events.models import Event
    from vendors.models import Vendor

    now = timezone.now()
    entries = [
        _url(absolute(reverse("events:home")), changefreq="daily", priority="1.0"),
        _url(absolute(reverse("events:list")), changefreq="daily", priority="0.9"),
        _url(absolute(reverse("events:vendor_calls")), changefreq="daily", priority="0.8"),
        _url(absolute(reverse("vendors:signup")), changefreq="monthly", priority="0.7"),
    ]
    # Published events: upcoming plus anything from the last 60 days. Older ones add little.
    events = Event.objects.filter(status=Event.Status.PUBLISHED, end_at__gte=now - timedelta(days=60)).order_by("-start_at")[:5000]
    for e in events:
        entries.append(_url(absolute(e.get_absolute_url()), lastmod=e.updated_at, changefreq="weekly", priority="0.8"))
    # Vendor pages only once they have something published (avoids thin empty pages).
    vendors = Vendor.objects.filter(user__is_active=True, events__status=Event.Status.PUBLISHED).distinct()[:5000]
    for v in vendors:
        entries.append(_url(absolute(reverse("vendors:profile", args=[v.slug])), changefreq="weekly", priority="0.6"))
    xml = '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">' + "".join(entries) + "</urlset>"
    return HttpResponse(xml, content_type="application/xml")


# ---------------------------------------------------------------------------
# Structured data. Only facts we actually store; nothing invented.
# ---------------------------------------------------------------------------
def dumps(data):
    """JSON safe to place inside <script type="application/ld+json">."""
    return json.dumps(data, ensure_ascii=False).replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")


def site_schema():
    org = {
        "@type": "Organization",
        "@id": absolute("/#org"),
        "name": settings.SITE_NAME,
        "alternateName": "popupplug",
        "url": absolute("/"),
        "logo": absolute(static("img/logo-512.png")),
    }
    if settings.INSTAGRAM_HANDLE:
        org["sameAs"] = [f"https://instagram.com/{settings.INSTAGRAM_HANDLE}"]
    site = {
        "@type": "WebSite",
        "@id": absolute("/#website"),
        "name": settings.SITE_NAME,
        "alternateName": "popupplug",
        "url": absolute("/"),
        "inLanguage": "en-NG",
        "publisher": {"@id": org["@id"]},
        "potentialAction": {
            "@type": "SearchAction",
            "target": {"@type": "EntryPoint", "urlTemplate": absolute("/events/?q={search_term_string}")},
            "query-input": "required name=search_term_string",
        },
    }
    return {"@context": "https://schema.org", "@graph": [org, site]}


def event_schema(event):
    url = absolute(event.get_absolute_url())
    data = {
        "@context": "https://schema.org",
        "@type": "Event",
        "name": event.title,
        "description": " ".join(event.description.split())[:500],
        "url": url,
        "startDate": timezone.localtime(event.start_at).isoformat(),
        "endDate": timezone.localtime(event.end_at).isoformat(),
        "eventStatus": "https://schema.org/EventScheduled",
        "eventAttendanceMode": "https://schema.org/OfflineEventAttendanceMode",
        "location": {
            "@type": "Place",
            "name": event.venue,
            "address": {
                "@type": "PostalAddress",
                "streetAddress": event.venue,
                "addressLocality": event.area.name,
                "addressRegion": "Lagos",
                "addressCountry": "NG",
            },
        },
        "image": [absolute_media(event.cover_image.url)],
        "organizer": {"@type": "Organization", "name": event.vendor.name, "url": absolute(reverse("vendors:profile", args=[event.vendor.slug]))},
        "isAccessibleForFree": bool(event.is_free_entry),
    }
    if event.is_free_entry:
        data["offers"] = {"@type": "Offer", "url": url, "price": "0", "priceCurrency": "NGN", "availability": "https://schema.org/InStock"}
    return data
