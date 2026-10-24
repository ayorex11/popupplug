"""Draws the 1080x1350 Instagram images and writes the captions. Pure Pillow, no network."""
import io
from pathlib import Path

from django.conf import settings
from django.core.files.base import ContentFile
from django.utils import timezone
from PIL import Image, ImageDraw, ImageFont, ImageOps

FONTS = Path(__file__).resolve().parent / "fonts"
W, H = 1080, 1350
INK, YELLOW, CORAL, CREAM, GREEN, GREEN_TINT = "#1B1B1B", "#FFC93C", "#FF5A36", "#FFF8EF", "#0F6B4F", "#E3F4EB"


def font(name, size):
    return ImageFont.truetype(str(FONTS / f"{name}.ttf"), size)


def wrap(draw, text, fnt, max_width, max_lines):
    words, lines, line = text.split(), [], ""
    for word in words:
        trial = f"{line} {word}".strip()
        if draw.textlength(trial, font=fnt) <= max_width:
            line = trial
        else:
            if line:
                lines.append(line)
            line = word
    if line:
        lines.append(line)
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        while lines[-1] and draw.textlength(lines[-1] + "...", font=fnt) > max_width:
            lines[-1] = lines[-1][:-1]
        lines[-1] = lines[-1].rstrip() + "..."
    return lines


def _shadow_box(draw, box, fill, radius=18, offset=8, width=5):
    x0, y0, x1, y1 = box
    draw.rounded_rectangle((x0 + offset, y0 + offset, x1 + offset, y1 + offset), radius, fill=INK)
    draw.rounded_rectangle(box, radius, fill=fill, outline=INK, width=width)


def _footer(draw):
    draw.rectangle((0, H - 96, W, H), fill=INK)
    draw.text((48, H - 48), "popupplug.com.ng", font=font("Bricolage-ExtraBold", 38), fill=YELLOW, anchor="lm")
    draw.text((W - 48, H - 48), f"@{settings.INSTAGRAM_HANDLE}", font=font("Jakarta-Bold", 32), fill="#FFFFFF", anchor="rm")


def _to_jpeg_file(img, name):
    buf = io.BytesIO()
    img.convert("RGB").save(buf, "JPEG", quality=90, optimize=True)
    return ContentFile(buf.getvalue(), name=name)


def render_event_card(event):
    img = Image.new("RGB", (W, H), YELLOW)
    d = ImageDraw.Draw(img)
    box = (48, 48, W - 48, 740)
    d.rounded_rectangle((box[0] + 10, box[1] + 10, box[2] + 10, box[3] + 10), 28, fill=INK)
    try:
        event.cover_image.open("rb")
        cover = Image.open(event.cover_image).convert("RGB")
        event.cover_image.close()
    except Exception:  # noqa: BLE001 - a missing image shouldn't stop the card being made
        cover = Image.new("RGB", (900, 600), CREAM)
    cover = ImageOps.fit(cover, (box[2] - box[0], box[3] - box[1]), Image.LANCZOS)
    mask = Image.new("L", cover.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, *cover.size), 28, fill=255)
    img.paste(cover, (box[0], box[1]), mask)
    d.rounded_rectangle(box, 28, outline=INK, width=6)

    start = timezone.localtime(event.start_at)
    # Date badge (yellow day header, white number), bottom-left of the photo
    bx, by = 80, 540
    _shadow_box(d, (bx, by, bx + 150, by + 170), "#FFFFFF", radius=16, offset=7)
    d.rounded_rectangle((bx, by, bx + 150, by + 52), 16, fill=YELLOW, outline=INK, width=5)
    d.rectangle((bx + 3, by + 30, bx + 147, by + 50), fill=YELLOW)
    d.text((bx + 75, by + 27), start.strftime("%a").upper(), font=font("Jakarta-ExtraBold", 30), fill=INK, anchor="mm")
    d.text((bx + 75, by + 108), start.strftime("%d").lstrip("0"), font=font("Bricolage-ExtraBold", 72), fill=INK, anchor="mm")
    d.text((bx + 75, by + 152), start.strftime("%b").upper(), font=font("Jakarta-ExtraBold", 24), fill=CORAL, anchor="mm")

    if event.is_free_entry:
        _shadow_box(d, (W - 330, 84, W - 84, 150), GREEN_TINT, radius=33, offset=5, width=4)
        d.text((W - 207, 117), "FREE ENTRY", font=font("Jakarta-ExtraBold", 32), fill=GREEN, anchor="mm")

    title_font = font("Bricolage-ExtraBold", 78)
    y = 790
    for line in wrap(d, event.title, title_font, W - 96, 2):
        d.text((48, y), line, font=title_font, fill=INK)
        y += 86
    y += 14
    info = font("Jakarta-Bold", 38)
    end = timezone.localtime(event.end_at)
    t = lambda x: x.strftime("%I:%M %p").lstrip("0")  # noqa: E731
    d.text((48, y), f"{start:%a %d %b}  |  {t(start)} - {t(end)}", font=info, fill=INK)
    y += 58
    where = f"{event.venue.split(',')[0]}, {event.area.name}"
    for line in wrap(d, where, font("Jakarta-Medium", 38), W - 96, 1):
        d.text((48, y), line, font=font("Jakarta-Medium", 38), fill="#3A3631")
    y += 58
    d.text((48, y), f"by {event.vendor.name}", font=font("Jakarta-Medium", 34), fill="#5C5750")
    _footer(d)
    return _to_jpeg_file(img, f"event-{event.pk}.jpg")


def render_welcome_card(vendor):
    img = Image.new("RGB", (W, H), YELLOW)
    d = ImageDraw.Draw(img)
    org = vendor.role == "organiser"
    both = vendor.role == "both"
    d.text((W // 2, 150), "NEW ORGANISER ON THE PLUG" if org else "NEW ON THE PLUG", font=font("Jakarta-ExtraBold", 40), fill=INK, anchor="mm")
    _shadow_box(d, (90, 250, W - 90, 930), "#FFFFFF", radius=36, offset=14, width=6)
    d.ellipse((W // 2 - 110, 310, W // 2 + 110, 530), fill=CORAL, outline=INK, width=6)
    d.text((W // 2, 420), vendor.initials, font=font("Bricolage-ExtraBold", 120), fill="#FFFFFF", anchor="mm")
    name_font = font("Bricolage-ExtraBold", 84)
    lines = wrap(d, vendor.name, name_font, W - 260, 2)
    y = 600 + (0 if len(lines) > 1 else 40)
    for line in lines:
        d.text((W // 2, y), line, font=name_font, fill=INK, anchor="mm")
        y += 96
    sub = "is now listing events on PopUp Plug" if org else ("is now selling and hosting on PopUp Plug" if both else "is now on PopUp Plug")
    d.text((W // 2, 840), sub, font=font("Jakarta-Bold", 40 if (org or both) else 44), fill="#5C5750", anchor="mm")
    line1, line2 = ("Events and vendors,", "all in one place.") if (org or both) else ("Pop-ups in Lagos,", "all in one place.")
    d.text((W // 2, 1060), line1, font=font("Bricolage-ExtraBold", 64), fill=INK, anchor="mm")
    d.text((W // 2, 1135), line2, font=font("Bricolage-ExtraBold", 64), fill=CORAL, anchor="mm")
    _footer(d)
    return _to_jpeg_file(img, f"welcome-{vendor.pk}.jpg")


HASHTAGS = "#LagosPopUp #LagosEvents #LagosVendors #SupportLocal #WhatsPoppingInLagos"


def event_caption(event):
    from core.notifications import absolute_url
    start = timezone.localtime(event.start_at)
    end = timezone.localtime(event.end_at)
    t = lambda x: x.strftime("%I:%M %p").lstrip("0")  # noqa: E731
    entry = "Free entry" if event.is_free_entry else (event.entry_note or "Paid entry")
    by = f"@{event.vendor.instagram}" if event.vendor.instagram else event.vendor.name
    return (
        f"{event.title}\n\n"
        f"When: {start:%a %d %b}, {t(start)} - {t(end)}\n"
        f"Where: {event.venue}, {event.area.name}\n"
        f"Entry: {entry}\n"
        f"By {by}\n\n"
        f"Full details: {absolute_url(event.get_absolute_url())} (link in bio)\n\n"
        f"Hosting a pop-up in Lagos? List it free at popupplug.com.ng\n\n{HASHTAGS}"
    )


def _kind(vendor):
    return vendor.role if vendor.role in ("organiser", "both") else "vendor"


def welcome_caption(vendor):
    who = f"@{vendor.instagram}" if vendor.instagram else vendor.name
    kind = _kind(vendor)
    if kind == "organiser":
        body = (f"Welcome to PopUp Plug, {who}!\n\n"
                f"Their events are now listed in Lagos, and vendors can see when booths are open. "
                f"Find them at popupplug.com.ng (link in bio).\n\n"
                f"Organising an event? List it free, and tell vendors you're taking applications.")
    elif kind == "both":
        body = (f"Welcome to PopUp Plug, {who}!\n\n"
                f"Follow along for their pop-ups and events in Lagos. See what's coming up at popupplug.com.ng (link in bio).\n\n"
                f"Hosting or selling at pop-ups? List it free.")
    else:
        body = (f"Welcome to PopUp Plug, {who}!\n\n"
                f"Follow along for their pop-ups in Lagos. See what's coming up at popupplug.com.ng (link in bio).\n\n"
                f"Hosting a pop-up? List it free.")
    return f"{body}\n\n{HASHTAGS}"


# ---------------------------------------------------------------------------
# TikTok and X drafts. Nothing is posted for you: staff copy these next to the downloaded card.
# ---------------------------------------------------------------------------
import re as _re

TIKTOK_MAX_HASHTAGS = 5
TIKTOK_MAX_CHARS = 2200
X_MAX_CHARS = 250  # counted literally, link included, so it's safe however X counts URLs

_HASHTAG = _re.compile(r"#\w+")


def limit_hashtags(text, n=TIKTOK_MAX_HASHTAGS):
    """Keep the first n hashtags and drop the rest."""
    seen = 0

    def keep(match):
        nonlocal seen
        seen += 1
        return match.group(0) if seen <= n else ""

    return _re.sub(r"[ \t]{2,}", " ", _HASHTAG.sub(keep, text)).strip()


def hashtag_count(text):
    return len(_HASHTAG.findall(text))


def _when_where(event):
    start = timezone.localtime(event.start_at)
    end = timezone.localtime(event.end_at)
    t = lambda x: x.strftime("%I:%M %p").lstrip("0")  # noqa: E731
    if start.date() == end.date():
        when = f"{start:%a %d %b}, {t(start)}"
    else:
        when = f"{start:%d %b} to {end:%d %b}"
    return when, f"{event.venue}, {event.area.name}"


def tiktok_event_caption(event):
    when, where = _when_where(event)
    entry = "Free entry" if event.is_free_entry else (event.entry_note or "Paid entry")
    tt = event.vendor.tiktok
    by = f"@{tt}" if tt else event.vendor.name
    text = (
        f"{event.title} 🎉\n"
        f"📍 {where}\n🗓 {when}\n🎟 {entry}\n"
        f"By {by}\n\n"
        f"Full details on popupplug.com.ng (link in bio)\n\n"
        f"{HASHTAGS}"
    )
    return limit_hashtags(text)[:TIKTOK_MAX_CHARS]


def tiktok_welcome_caption(vendor):
    who = f"@{vendor.tiktok}" if vendor.tiktok else vendor.name
    kind = _kind(vendor)
    if kind == "organiser":
        line = "Their events are now listed in Lagos, and vendors can see when booths are open. Details at popupplug.com.ng (link in bio).\nOrganising an event? List it free."
    elif kind == "both":
        line = "Find their pop-ups and events in Lagos at popupplug.com.ng (link in bio).\nHosting or selling at pop-ups? List it free."
    else:
        line = "Find their pop-ups in Lagos at popupplug.com.ng (link in bio).\nHosting a pop-up? List it free."
    text = f"Welcome to PopUp Plug, {who}! 🎉\n{line}\n\n{HASHTAGS}"
    return limit_hashtags(text)[:TIKTOK_MAX_CHARS]


def _fit(parts, optional, limit):
    """Join the required lines, then add each optional line only while it still fits."""
    text = "\n".join(p for p in parts if p)
    for extra in optional:
        trial = f"{text}\n{extra}" if extra else text
        if extra and len(trial) <= limit:
            text = trial
    return text


def x_event_post(event):
    from core.notifications import absolute_url
    when, where = _when_where(event)
    link = absolute_url(event.get_absolute_url())
    entry = "Free entry" if event.is_free_entry else ""
    tw = event.vendor.twitter
    by = f"By @{tw}" if tw else ""
    tail = f"{when}\n{event.area.name}\n{link}"
    # Title gets whatever room is left, so the date, area and link are never cut off.
    room = X_MAX_CHARS - len(tail) - 1
    title = event.title if len(event.title) <= room else event.title[: max(room - 1, 1)].rstrip() + "…"
    text = _fit([title, when, event.area.name, link], [entry, by], X_MAX_CHARS)
    for tags in ("#LagosPopUp #WhatsPoppingInLagos", "#LagosPopUp"):  # the longest set that still fits
        if len(text) + 1 + len(tags) <= X_MAX_CHARS:
            text += "\n" + tags
            break
    return text[:X_MAX_CHARS]


def x_welcome_post(vendor):
    from django.conf import settings
    who = f"@{vendor.twitter}" if vendor.twitter else vendor.name
    kind = _kind(vendor)
    what = {"organiser": "See their events and open booths", "both": "See their pop-ups and events"}.get(kind, "See their Lagos pop-ups")
    text = _fit([f"Welcome to PopUp Plug, {who}!", f"{what}: {settings.SITE_URL}"], [], X_MAX_CHARS)
    if len(text) + 1 + len("#LagosPopUp") <= X_MAX_CHARS:
        text += "\n#LagosPopUp"
    return text[:X_MAX_CHARS]
