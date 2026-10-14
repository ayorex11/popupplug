from django.contrib import messages
from django.contrib.auth.signals import user_logged_in, user_logged_out
from django.dispatch import receiver


@receiver(user_logged_in)
def _welcome_back(sender, request, user, **kwargs):
    # Signup logs the user in too and shows its own welcome message.
    if request is not None and hasattr(request, "_messages") and request.path.startswith("/login"):
        messages.success(request, "You're logged in.")


@receiver(user_logged_out)
def _bye(sender, request, **kwargs):
    if request is not None and hasattr(request, "_messages"):
        messages.success(request, "You've been logged out.")
