from django.db.models.signals import post_save
from django.dispatch import receiver

from core.notifications import notify_new_vendor

from .models import Vendor


@receiver(post_save, sender=Vendor)
def vendor_created(sender, instance, created, **kwargs):
    if created and not instance.verified:
        notify_new_vendor(instance)
