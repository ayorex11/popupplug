from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from .caching import bump_version
from .models import Event


@receiver([post_save, post_delete], sender=Event)
def invalidate_public_pages(sender, **kwargs):
    # Skip the bump for pure counter updates (Interested toggles use queryset.update, which
    # doesn't fire post_save anyway), so only real edits invalidate the cached pages.
    bump_version()
