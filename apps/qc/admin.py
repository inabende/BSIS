from django.contrib import admin
from simple_history.admin import SimpleHistoryAdmin

from .models import FinalResult, QCSettings


@admin.register(QCSettings)
class QCSettingsAdmin(SimpleHistoryAdmin):
    list_display = ("project", "density_threshold_pct", "final_rule")


@admin.register(FinalResult)
class FinalResultAdmin(SimpleHistoryAdmin):
    """Read-only: final results are worked out from readings, and locked/unlocked from the slide page."""

    list_display = ("slide", "is_positive", "species", "density_per_ul", "had_discordance", "locked")
    list_filter = ("locked", "had_discordance", "slide__project")
    search_fields = ("slide__slide_id",)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
