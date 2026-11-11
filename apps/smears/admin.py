from django.contrib import admin
from simple_history.admin import SimpleHistoryAdmin

from .models import FieldDefinition, Reading, SmearType, Slide


class FieldDefinitionInline(admin.StackedInline):
    model = FieldDefinition
    extra = 0
    fields = [
        ("key", "label", "data_type"),
        ("required", "required_if_positive", "is_active", "order"),
        ("unit", "min_value", "max_value"),
        "help_text",
        "choices",
    ]

    def has_delete_permission(self, request, obj=None):
        # Saved readings refer to fields by key; deactivate a field instead of deleting it.
        return False


@admin.register(SmearType)
class SmearTypeAdmin(SimpleHistoryAdmin):
    list_display = ("name", "code", "slide_suffix", "calculation", "is_builtin", "is_active", "order")
    list_filter = ("is_active", "is_builtin")
    inlines = [FieldDefinitionInline]

    def get_readonly_fields(self, request, obj=None):
        if obj and obj.is_builtin:
            return ("code", "calculation")
        return ()

    def has_delete_permission(self, request, obj=None):
        # Deactivate instead; existing slides keep their type.
        return False


class ReadingInline(admin.TabularInline):
    model = Reading
    extra = 0
    fields = ("reader_number", "reader", "read_at", "is_positive", "species", "density_per_ul", "parasitaemia_pct")
    readonly_fields = fields
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Slide)
class SlideAdmin(SimpleHistoryAdmin):
    list_display = ("slide_id", "smear_type", "sample", "project", "status", "created_at")
    list_filter = ("project", "smear_type", "status")
    search_fields = ("slide_id", "sample__sample_id")
    readonly_fields = ("project", "created_by", "created_at", "updated_at")
    inlines = [ReadingInline]
