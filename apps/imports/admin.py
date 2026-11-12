from django.contrib import admin
from simple_history.admin import SimpleHistoryAdmin

from .models import ImportBatch


@admin.register(ImportBatch)
class ImportBatchAdmin(SimpleHistoryAdmin):
    list_display = ("pk", "original_name", "project", "smear_type", "status", "rows_total", "rows_imported",
                    "uploaded_by", "created_at")
    list_filter = ("status", "project", "smear_type")
    readonly_fields = [f.name for f in ImportBatch._meta.fields] + ["slides"]

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
