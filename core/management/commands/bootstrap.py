"""One command that makes a fresh database ready: migrate, seed Lagos data, create the admin."""
from django.core.management import call_command
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "migrate + seed_lagos + ensure_admin (run on every deploy by build.sh)."

    def handle(self, *args, **options):
        call_command("migrate", interactive=False, verbosity=1)
        call_command("seed_lagos")
        call_command("ensure_admin")
