from django.core.management.base import BaseCommand
from django.utils.text import slugify

from events.models import Area, Category, City

AREAS = [
    "Lekki", "Victoria Island", "Ikoyi", "Ajah", "Yaba", "Surulere", "Ikeja", "Maryland",
    "Gbagada", "Magodo", "Festac", "Ikorodu", "Oshodi", "Apapa", "Badagry", "Epe",
    "Ojodu", "Egbeda", "Ogba", "Isolo", "Mushin", "Lagos Island", "Idimu", "Oniru", "Alimosho",
    "Ikotun", "Agege", "Ejigbo", "Okota", "Ketu", "Ojota", "Ilupeju", "Lekki Phase 1",
]

CATEGORIES = [
    "Fashion & Clothing", "Cakes & Pastries", "Food & Drinks", "Beauty & Makeup",
    "Art & Crafts", "Thrift & Vintage", "Home & Decor", "Books", "Tech & Gadgets",
    "Kids", "Wellness", "Other",
]


class Command(BaseCommand):
    help = "Seed Lagos, its neighborhoods, and starter categories (safe to re-run)."

    def handle(self, *args, **options):
        city, _ = City.objects.get_or_create(slug="lagos", defaults={"name": "Lagos"})
        for name in AREAS:
            Area.objects.get_or_create(city=city, slug=slugify(name), defaults={"name": name})
        for name in CATEGORIES:
            Category.objects.get_or_create(slug=slugify(name), defaults={"name": name})
        if options.get("verbosity", 1) > 0:
            self.stdout.write(self.style.SUCCESS(
                f"Seeded {Area.objects.count()} areas and {Category.objects.count()} categories."
            ))
