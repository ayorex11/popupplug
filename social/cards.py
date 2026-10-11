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
    d.text((W // 2, 150), "NEW ON THE PLUG", font=font("Jakarta-ExtraBold", 40), fill=INK, anchor="mm")
    _shadow_box(d, (90, 250, W - 90, 930), "#FFFFFF", radius=36, offset=14, width=6)
    d.ellipse((W // 2 - 110, 310, W // 2 + 110, 530), fill=CORAL, outline=INK, width=6)
    d.text((W // 2, 420), vendor.initials, font=font("Bricolage-ExtraBold", 120), fill="#FFFFFF", anchor="mm")
    name_font = font("Bricolage-ExtraBold", 84)
    lines = wrap(d, vendor.name, name_font, W - 260, 2)
    y = 600 + (0 if len(lines) > 1 else 40)
    for line in lines:
        d.text((W // 2, y), line, font=name_font, fill=INK, anchor="mm")
        y += 96
    d.text((W // 2, 840), "is now on PopUp Plug", font=font("Jakarta-Bold", 44), fill="#5C5750", anchor="mm")
    d.text((W // 2, 1060), "Pop-ups in Lagos,", font=font("Bricolage-ExtraBold", 64), fill=INK, anchor="mm")
    d.text((W // 2, 1135), "all in one place.", font=font("Bricolage-ExtraBold", 64), fill=CORAL, anchor="mm")
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


def welcome_caption(vendor):
    who = f"@{vendor.instagram}" if vendor.instagram else vendor.name
    return (
        f"Welcome to PopUp Plug, {who}!\n\n"
        f"Follow along for their pop-ups in Lagos. See what's coming up at popupplug.com.ng (link in bio).\n\n"
        f"Hosting a pop-up? List it free.\n\n{HASHTAGS}"
    )
