from django.contrib import admin
from django.utils.html import format_html

from .models import Area, Category, City, Event, Interested


@admin.register(City)
class CityAdmin(admin.ModelAdmin):
    list_display = ("name", "is_active")
    prepopulated_fields = {"slug": ("name",)}


@admin.register(Area)
class AreaAdmin(admin.ModelAdmin):
    list_display = ("name", "city")
    list_filter = ("city",)
    prepopulated_fields = {"slug": ("name",)}


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    prepopulated_fields = {"slug": ("name",)}


@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    """This is the moderation dashboard: filter by 'Pending review' and approve in bulk."""

    list_display = ("title", "vendor", "area", "category", "start_at", "status", "interested_count", "thumb")
    list_filter = ("status", "area", "category", "is_free_entry")
    search_fields = ("title", "vendor__name", "venue")
    date_hierarchy = "start_at"
    readonly_fields = ("slug", "interested_count", "created_at", "updated_at", "thumb")
    list_select_related = ("vendor", "area", "category")
    actions = ["approve", "reject"]

    @admin.display(description="Cover")
    def thumb(self, obj):
        if obj.cover_image:
            return format_html('<img src="{}" style="height:48px;border-radius:4px">', obj.cover_image.url)
        return "-"

    @admin.action(description="Approve and publish selected events")
    def approve(self, request, queryset):
        updated = queryset.update(status=Event.Status.PUBLISHED)
        from .caching import bump_version
        bump_version()
        self.message_user(request, f"{updated} event(s) published.")

    @admin.action(description="Reject selected events")
    def reject(self, request, queryset):
        updated = queryset.update(status=Event.Status.REJECTED)
        from .caching import bump_version
        bump_version()
        self.message_user(request, f"{updated} event(s) rejected.")


@admin.register(Interested)
class InterestedAdmin(admin.ModelAdmin):
    list_display = ("event", "user", "created_at")
    readonly_fields = ("event", "user", "session_key", "created_at")
