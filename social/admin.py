from django.contrib import admin

from .models import SocialPost


@admin.register(SocialPost)
class SocialPostAdmin(admin.ModelAdmin):
    list_display = ("id", "kind", "status", "event", "vendor", "created_at")
    list_filter = ("kind", "status")
