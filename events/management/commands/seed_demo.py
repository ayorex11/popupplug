"""Fill a LOCAL database with sample vendors and events so you can see the site populated.

    python manage.py seed_demo          # creates demo data (no emails are sent)
    python manage.py seed_demo --clear  # removes it again

Demo vendors use @example.invalid emails and are easy to spot. Never run this on production.
"""
import io
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.utils import timezone
from PIL import Image, ImageDraw

from core.notifications import muted
from events.models import Area, Category, Event
from vendors.models import Vendor

User = get_user_model()
DEMO = "@example.invalid"
PALETTES = [("#FF5A36", "#FFC93C"), ("#0F6B4F", "#FFC93C"), ("#1B1B1B", "#FF5A36"), ("#FFC93C", "#0F6B4F"), ("#B52603", "#FFE8E2")]

VENDORS = [
    ("Smoky Lagos Grills", "08031234567", "smokylagosgrills"),
    ("Ade's Thrift Co.", "08052345678", "adesthrift"),
    ("Teni's Treats", "08093456789", "tenistreats"),
    ("Adire & Glow", "07014567890", "adireandglow"),
]
EVENTS = [
    ("Suya Shack Cookout", "Food & Drinks", "Ikeja", "JJT Park, Alausa", 0, 3, True, ""),
    ("Y2K Vintage Thrift Yard", "Thrift & Vintage", "Victoria Island", "Muri Okunola Park", 1, 6, True, ""),
    ("Weekend Bakes Market", "Cakes & Pastries", "Ikeja", "Ikeja GRA Open Gardens", 2, 10, False, "Gate fee N1,000"),
    ("Afro-Luxury Booth", "Fashion & Clothing", "Lekki", "The Palms Courtyard", 3, 4, True, ""),
    ("Sneaker and Cap Exchange", "Fashion & Clothing", "Yaba", "Herbert Macaulay Way", 1, 14, True, ""),
    ("Candle and Perfume Bar", "Beauty & Makeup", "Lekki", "Admiralty Way", 3, 18, True, ""),
]


def flyer(i, title):
    a, b = PALETTES[i % len(PALETTES)]
    img = Image.new("RGB", (1000, 625), a)
    d = ImageDraw.Draw(img)
    d.ellipse((620, -120, 1120, 380), fill=b)
    d.ellipse((-140, 360, 300, 800), fill=b)
    buf = io.BytesIO()
    img.save(buf, "WEBP", quality=80)
    return ContentFile(buf.getvalue(), name="demo.webp")


class Command(BaseCommand):
    help = "Create (or --clear) demo vendors and events for local development."

    def add_arguments(self, parser):
        parser.add_argument("--clear", action="store_true")

    def handle(self, *args, **opts):
        if opts["clear"]:
            n = User.objects.filter(email__endswith=DEMO).delete()[0]
            self.stdout.write(f"Removed demo data ({n} rows).")
            return
        call_command("seed_lagos", verbosity=0)
        now = timezone.now().replace(minute=0, second=0, microsecond=0)
        with muted():
            vendors = []
            for name, phone, ig in VENDORS:
                email = f"{ig}{DEMO}"
                user, _ = User.objects.get_or_create(username=email, defaults={"email": email})
                v, _ = Vendor.objects.get_or_create(user=user, defaults={"name": name, "phone": phone, "instagram": ig, "verified": True})
                vendors.append(v)
            for i, (title, cat, area, venue, vi, days, free, note) in enumerate(EVENTS):
                if Event.objects.filter(title=title, vendor=vendors[vi]).exists():
                    continue
                start = now + timedelta(days=days, hours=2)
                e = Event(vendor=vendors[vi], title=title, category=Category.objects.get(name=cat), area=Area.objects.get(name=area),
                          venue=venue, description=f"{title}. Come through, bring friends, shop local. (Demo listing.)",
                          start_at=start, end_at=start + timedelta(hours=7), is_free_entry=free, entry_note=note,
                          status=Event.Status.PUBLISHED if i != 4 else Event.Status.PENDING)
                e.cover_image.save("demo.webp", flyer(i, title), save=False)
                e.save()
            # one unverified vendor so the desk has something to approve
            user, _ = User.objects.get_or_create(username=f"newvendor{DEMO}", defaults={"email": f"newvendor{DEMO}"})
            Vendor.objects.get_or_create(user=user, defaults={"name": "Mama Put Pop-Ups", "phone": "08111222333", "instagram": "mamaput"})
        self.stdout.write("Demo data created. Remove with: python manage.py seed_demo --clear")
