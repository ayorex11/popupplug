from django.contrib import admin

from .models import Entry, Giveaway


@admin.register(Giveaway)
class GiveawayAdmin(admin.ModelAdmin):
    list_display = ("event", "prize", "winner_count", "closes_at", "state", "drawn_at")
    readonly_fields = ("drawn_at",)
    autocomplete_fields = ()

    @admin.display(description="State")
    def state(self, obj):
        return obj.state


@admin.register(Entry)
class EntryAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "phone", "giveaway", "result", "excluded", "created_at")
    list_filter = ("giveaway", "result", "excluded")
    search_fields = ("name", "phone", "code")
    readonly_fields = ("code", "ip_hash", "created_at")
