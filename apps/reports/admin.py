from django.contrib import admin

from .models import ExportLog


@admin.register(ExportLog)
class ExportLogAdmin(admin.ModelAdmin):
    """Read-only record of data exports."""

    list_display = ("created_at", "user", "format", "slide_count", "reading_count", "projects")
    list_filter = ("format", "user")
    readonly_fields = [f.name for f in ExportLog._meta.fields]

    @admin.display(description="Projects")
    def projects(self, obj):
        return ", ".join(obj.project_codes)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
