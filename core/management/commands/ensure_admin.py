"""Create or update the admin account from ADMIN_EMAIL / ADMIN_PASSWORD.

Render's free plan has no shell, so this runs on every deploy (see build.sh).
It is safe to run repeatedly: it never touches an existing password unless
ADMIN_PASSWORD is set, and it does nothing if ADMIN_EMAIL is not set.
"""
import os

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Create/update the superuser from ADMIN_EMAIL and ADMIN_PASSWORD."

    def handle(self, *args, **options):
        email = os.environ.get("ADMIN_EMAIL", "").strip().lower()
        password = os.environ.get("ADMIN_PASSWORD", "")
        if not email:
            self.stdout.write("ensure_admin: ADMIN_EMAIL not set, skipping.")
            return
        User = get_user_model()
        user = User.objects.filter(username=email).first() or User.objects.filter(email__iexact=email, is_superuser=True).first()
        created = user is None
        if created:
            if not password:
                self.stdout.write("ensure_admin: ADMIN_PASSWORD not set, cannot create the admin.")
                return
            user = User(username=email)
        user.email = email
        user.is_staff = user.is_superuser = user.is_active = True
        if password:
            user.set_password(password)
        user.save()
        self.stdout.write(f"ensure_admin: {'created' if created else 'updated'} admin {email}")
