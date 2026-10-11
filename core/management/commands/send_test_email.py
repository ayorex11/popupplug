from django.core.management.base import BaseCommand

from core.notifications import admin_recipients, send_card_email


class Command(BaseCommand):
    help = "Send a test email to confirm SMTP works. Usage: manage.py send_test_email [address]"

    def add_arguments(self, parser):
        parser.add_argument("to", nargs="?", help="Defaults to your admin notification address(es).")

    def handle(self, *args, **options):
        to = [options["to"]] if options["to"] else admin_recipients()
        if not to:
            self.stderr.write("No recipient: pass an address, or set ADMIN_NOTIFY_EMAILS / ADMIN_EMAIL.")
            return
        from django.conf import settings
        from django.db import transaction
        settings.NOTIFY_ASYNC = False  # so we see errors and exit only when it's sent
        with transaction.atomic():
            send_card_email(
                "PopUp Plug test email", "Email is working",
                "If you can read this, new-vendor alerts will reach you.",
                [("Sent to", ", ".join(to)), ("Backend", settings.EMAIL_BACKEND.rsplit(".", 2)[-2])],
                to, "Open the site", "/",
            )
        self.stdout.write(f"Test email sent to {', '.join(to)} (check the Render logs if nothing arrives).")
