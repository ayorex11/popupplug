from django.contrib import admin

from .models import Vendor


@admin.register(Vendor)
class VendorAdmin(admin.ModelAdmin):
    list_display = ("name", "role", "phone", "instagram", "tiktok", "twitter", "verified", "created_at")
    list_filter = ("verified", "role")
    search_fields = ("name", "phone", "instagram", "tiktok", "twitter", "website", "user__email", "user__username")
    list_editable = ("verified",)
    readonly_fields = ("created_at",)
    actions = ["mark_verified"]

    @admin.action(description="Mark selected vendors as verified")
    def mark_verified(self, request, queryset):
        updated = queryset.update(verified=True)
        self.message_user(request, f"{updated} vendor(s) verified.")
